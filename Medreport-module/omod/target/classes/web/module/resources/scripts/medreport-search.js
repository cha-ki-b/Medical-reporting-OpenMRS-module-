/*
 * Cross-patient report search.
 *
 * Answers the clinical question the per-patient panel cannot: "show me everything user2 wrote
 * about studies 5 and 6". The two filters are independent SETS and they intersect - authors
 * AND images - which is why both are checkbox lists rather than single-value selects.
 *
 * Both lists are populated from what actually exists in the reports (distinct authors,
 * distinct covered studies), so they stay short and every entry returns at least one result.
 *
 * As everywhere in this module, the per-report canEdit/canRemove flags come from the server
 * on every response. They decide what renders; the server decides what is permitted.
 */
var medreportSearch = (function () {
    'use strict';

    var cfg = {};
    var authors = [];
    var images = [];

    var SEP = ' · ';

    function $(id) { return document.getElementById(id); }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        // textContent: report text is clinician-authored and study descriptions come from
        // DICOM. Neither is markup we control.
        if (text !== undefined && text !== null) { node.textContent = text; }
        return node;
    }

    function m(key) { return (cfg.messages && cfg.messages[key]) || key; }

    function readJson(response) {
        return response.json().catch(function () {
            return { success: false, message: 'HTTP ' + response.status };
        }).then(function (body) {
            if (!response.ok || body.success === false) {
                throw new Error(body.message || ('HTTP ' + response.status));
            }
            return body;
        });
    }

    function get(url) {
        return fetch(url, { credentials: 'same-origin' }).then(readJson);
    }

    function notify(kind, text) {
        var box = $('mr-search-notice');
        if (!box) { return; }
        box.className = 'mr-note mr-note-' + kind;
        box.textContent = text;
        box.hidden = false;
    }

    function clearNotice() {
        var box = $('mr-search-notice');
        if (box) { box.hidden = true; }
    }

    // ---------------------------------------------------------------
    // filters
    // ---------------------------------------------------------------

    function renderFilters() {
        renderCheckList($('mr-author-list'), authors, 'author', function (a) {
            return a.label || a.username;
        });
        renderCheckList($('mr-image-list'), images, 'image', function (i) {
            return i.label || i.studyUid;
        });
        updateCounts();
    }

    function renderCheckList(host, items, kind, labelOf) {
        if (!host) { return; }
        host.innerHTML = '';
        if (!items.length) {
            host.appendChild(el('p', 'mr-empty', '-'));
            return;
        }
        items.forEach(function (item, index) {
            var row = el('label', 'mr-check');
            var box = document.createElement('input');
            box.type = 'checkbox';
            box.dataset.mrKind = kind;
            box.dataset.mrIndex = String(index);
            box.addEventListener('change', updateCounts);
            row.appendChild(box);
            row.appendChild(el('span', null, labelOf(item)));
            host.appendChild(row);
        });
    }

    function checkedIndexes(kind) {
        return Array.prototype.slice
            .call(document.querySelectorAll('input[data-mr-kind="' + kind + '"]'))
            .filter(function (box) { return box.checked; })
            .map(function (box) { return parseInt(box.dataset.mrIndex, 10); });
    }

    function updateCounts() {
        var a = checkedIndexes('author').length;
        var i = checkedIndexes('image').length;
        var authorBadge = $('mr-author-count');
        var imageBadge = $('mr-image-count');
        if (authorBadge) { authorBadge.textContent = a + ' ' + m('selected'); }
        if (imageBadge) { imageBadge.textContent = i + ' ' + m('selected'); }
    }

    function clearFilters() {
        Array.prototype.slice.call(document.querySelectorAll('input[data-mr-kind]'))
            .forEach(function (box) { box.checked = false; });
        var mine = $('mr-mine-only');
        if (mine) { mine.checked = false; }
        updateCounts();
        search();
    }

    // ---------------------------------------------------------------
    // search
    // ---------------------------------------------------------------

    function search() {
        clearNotice();
        var button = $('mr-search');
        if (button) { button.disabled = true; }

        var authorIds = checkedIndexes('author').map(function (i) { return authors[i].id; });
        var studyUids = checkedIndexes('image').map(function (i) { return images[i].studyUid; });
        var mine = $('mr-mine-only') && $('mr-mine-only').checked;

        var params = [];
        // "mine" is resolved server-side from the session, so no author id is sent for it.
        if (!mine && authorIds.length) {
            params.push('authorIds=' + encodeURIComponent(authorIds.join(',')));
        }
        if (studyUids.length) {
            params.push('studyUids=' + encodeURIComponent(studyUids.join(',')));
        }
        if (mine) { params.push('mine=true'); }

        var host = $('mr-results');
        if (host) {
            host.innerHTML = '';
            host.appendChild(el('p', 'mr-empty', m('searching')));
        }

        get(cfg.base + '/reportSearch.form?' + params.join('&'))
            .then(function (body) {
                renderResults(body.reports || []);
            })
            .catch(function (error) {
                notify('error', error.message);
                renderResults([]);
            })
            .then(function () {
                if (button) { button.disabled = false; }
            });
    }

    function renderResults(reports) {
        var host = $('mr-results');
        if (!host) { return; }
        host.innerHTML = '';

        var counter = $('mr-result-count');
        if (counter) {
            counter.textContent = reports.length + ' ' + m('results');
        }

        if (!reports.length) {
            host.appendChild(el('p', 'mr-empty', m('none')));
            return;
        }
        reports.forEach(function (report) {
            host.appendChild(renderReport(report));
        });
    }

    function renderReport(report) {
        var current = report.current || {};
        var card = el('div', 'mr-report'
            + (report.isOwn ? ' mr-own' : '')
            + (report.voided ? ' mr-removed' : ''));

        var head = el('div', 'mr-report-head');
        head.appendChild(el('span', 'mr-report-title', current.title || '-'));
        if (report.isOwn) {
            head.appendChild(el('span', 'mr-tag mr-tag-own', m('own')));
        }
        if (report.voided) {
            head.appendChild(el('span', 'mr-tag mr-tag-removed', m('removed')));
        }
        card.appendChild(head);

        // Cross-patient results are unusable without saying whose record each row is.
        var patient = report.patient || {};
        var patientLine = el('div', 'mr-meta');
        patientLine.appendChild(document.createTextNode(m('patient') + ' : '));
        patientLine.appendChild(el('strong', null,
            [patient.familyName, patient.givenName].filter(Boolean).join(' ') || '-'));
        if (patient.identifier) {
            patientLine.appendChild(document.createTextNode(SEP + patient.identifier));
        }
        card.appendChild(patientLine);

        var meta = el('div', 'mr-meta');
        meta.appendChild(document.createTextNode(m('author') + ' : '));
        meta.appendChild(el('strong', null, report.author || '-'));
        meta.appendChild(document.createTextNode(
            SEP + (current.dateCreated || '') + SEP + m('version') + ' ' + (current.versionNumber || 1)));
        card.appendChild(meta);

        if (current.observationText) {
            card.appendChild(el('div', 'mr-report-text', current.observationText));
        }

        if (current.images && current.images.length) {
            var chips = el('div', 'mr-images');
            current.images.forEach(function (image) {
                chips.appendChild(el('span', 'mr-image-chip', image.label || image.studyUid));
            });
            card.appendChild(chips);
        }

        card.appendChild(renderActions(report, current, patient));
        return card;
    }

    function renderActions(report, current, patient) {
        var actions = el('div', 'mr-report-actions');

        if (current.hasDocument) {
            var download = el('a', 'mr-btn mr-btn-small', m('download'));
            download.href = cfg.base + '/imageReportDocument.form?versionUuid='
                          + encodeURIComponent(current.uuid);
            actions.appendChild(download);
        }

        // Editing happens on the patient's own imaging-reports page, which already has the
        // image picker and the full editor. Duplicating that here would mean two editors to
        // keep in step, so this links across instead.
        if (patient.id) {
            var open = el('a', 'mr-btn mr-btn-small', m('open'));
            open.href = '/' + OPENMRS_CONTEXT_PATH
                      + '/medreport/imagingReports.page?patientId=' + encodeURIComponent(patient.id);
            actions.appendChild(open);
        }

        // Shown disabled with a reason on someone else's report rather than hidden, so it
        // reads as "not yours" instead of a missing feature. The server enforces it anyway.
        var edit = el('button', 'mr-btn mr-btn-small', m('edit'));
        edit.type = 'button';
        if (report.canEdit && patient.id) {
            edit.addEventListener('click', function () {
                window.location.href = '/' + OPENMRS_CONTEXT_PATH
                    + '/medreport/imagingReports.page?patientId=' + encodeURIComponent(patient.id);
            });
        } else {
            edit.disabled = true;
            edit.title = report.isOwn ? '' : m('notOwner');
        }
        actions.appendChild(edit);

        return actions;
    }

    // ---------------------------------------------------------------
    // bootstrap
    // ---------------------------------------------------------------

    function init(options) {
        cfg = options || {};

        var searchButton = $('mr-search');
        if (searchButton) { searchButton.addEventListener('click', search); }
        var clearButton = $('mr-clear');
        if (clearButton) { clearButton.addEventListener('click', clearFilters); }
        var mine = $('mr-mine-only');
        if (mine) { mine.addEventListener('change', search); }

        get(cfg.base + '/reportFilters.form')
            .then(function (body) {
                authors = body.authors || [];
                images = body.images || [];
                renderFilters();
                // Land on something useful rather than an empty screen.
                search();
            })
            .catch(function (error) {
                notify('error', error.message);
            });
    }

    return { init: init, search: search };
}());
