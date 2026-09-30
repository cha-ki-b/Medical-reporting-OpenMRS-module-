/*
 * Cross-patient report search.
 *
 * Answers the clinical question the per-patient panel cannot: "show me everything user2 wrote
 * about studies 5 and 6". The two filters are independent SETS and they intersect.
 *
 * Why token fields instead of checkbox lists
 * ------------------------------------------
 * The first version rendered a checkbox per author and per image. That works for a demo and
 * fails completely in production: Orthanc holds thousands of studies, so the filter panel
 * became an unusable 2000-row scroll, and it fetched the entire catalogue on every page load.
 * Here the widget shows only what has been *selected*, as removable chips, and queries the
 * server as the user types. Its size is bounded by the selection, not by the catalogue.
 *
 * As everywhere in this module, the per-report canEdit/canRemove flags come from the server
 * on every response. They decide what renders; the server decides what is permitted.
 */
var medreportSearch = (function () {
    'use strict';

    var cfg = {};
    var SEP = ' · ';
    var DEBOUNCE_MS = 220;

    /* Selected tokens, by filter. Values are {id|studyUid, label}. */
    var selection = { author: [], image: [] };

    function $(id) { return document.getElementById(id); }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) { node.className = className; }
        // textContent, never innerHTML: report text is clinician-authored and study
        // descriptions come from DICOM. Neither is markup we control.
        if (text !== undefined && text !== null) { node.textContent = text; }
        return node;
    }

    function m(key) { return (cfg.messages && cfg.messages[key]) || key; }

    // ---------------------------------------------------------------
    // transport
    // ---------------------------------------------------------------

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
    // token fields
    // ---------------------------------------------------------------

    function tokenKey(kind, item) {
        return kind === 'author' ? String(item.id) : String(item.studyUid);
    }

    function isSelected(kind, item) {
        var key = tokenKey(kind, item);
        return selection[kind].some(function (chosen) {
            return tokenKey(kind, chosen) === key;
        });
    }

    function addToken(kind, item) {
        if (!isSelected(kind, item)) {
            selection[kind].push(item);
            renderTokens(kind);
            search();
        }
    }

    function removeToken(kind, item) {
        var key = tokenKey(kind, item);
        selection[kind] = selection[kind].filter(function (chosen) {
            return tokenKey(kind, chosen) !== key;
        });
        renderTokens(kind);
        search();
    }

    function renderTokens(kind) {
        var field = $('mr-' + kind + '-field');
        var input = $('mr-' + kind + '-input');
        if (!field || !input) { return; }

        // Rebuild the chips in place, always leaving the input as the last child so typing
        // continues where the user expects.
        Array.prototype.slice.call(field.querySelectorAll('.mr-token'))
            .forEach(function (node) { node.remove(); });

        selection[kind].forEach(function (item) {
            var token = el('span', 'mr-token');
            token.appendChild(el('span', null, item.label));

            var close = el('button', null, '×');
            close.type = 'button';
            close.setAttribute('aria-label', m('remove') + ' ' + item.label);
            close.addEventListener('click', function () { removeToken(kind, item); });
            token.appendChild(close);

            field.insertBefore(token, input);
        });
    }

    /* --- suggestions ------------------------------------------------ */

    var timers = {};
    var activeIndex = {};

    function querySuggestions(kind) {
        var input = $('mr-' + kind + '-input');
        var box = $('mr-' + kind + '-suggest');
        if (!input || !box) { return; }

        var url = cfg.base + '/filterSearch.form?kind=' + (kind === 'author' ? 'authors' : 'images')
                + '&q=' + encodeURIComponent(input.value.trim());

        get(url).then(function (body) {
            var items = (kind === 'author' ? body.authors : body.images) || [];
            renderSuggestions(kind, items);
        }).catch(function (error) {
            notify('error', error.message);
        });
    }

    function renderSuggestions(kind, items) {
        var box = $('mr-' + kind + '-suggest');
        var input = $('mr-' + kind + '-input');
        if (!box) { return; }

        box.innerHTML = '';
        activeIndex[kind] = -1;

        var available = items.filter(function (item) { return !isSelected(kind, item); });

        if (!available.length) {
            box.appendChild(el('div', 'mr-suggest-empty', m('noMatch')));
        } else {
            available.forEach(function (item, index) {
                var option = el('button', 'mr-suggest-item');
                option.type = 'button';
                option.setAttribute('role', 'option');
                option.dataset.mrIndex = String(index);
                option.appendChild(el('strong', null, item.label));
                if (item.username) {
                    option.appendChild(el('span', 'mr-meta', item.username));
                }
                option.addEventListener('click', function () {
                    addToken(kind, item);
                    input.value = '';
                    hideSuggestions(kind);
                    input.focus();
                });
                box.appendChild(option);
            });
            // The server caps the page; say so rather than implying this is everything.
            if (available.length >= 15) {
                box.appendChild(el('div', 'mr-suggest-more', m('more')));
            }
        }

        box.hidden = false;
        if (input) { input.setAttribute('aria-expanded', 'true'); }
    }

    function hideSuggestions(kind) {
        var box = $('mr-' + kind + '-suggest');
        var input = $('mr-' + kind + '-input');
        if (box) { box.hidden = true; }
        if (input) { input.setAttribute('aria-expanded', 'false'); }
        activeIndex[kind] = -1;
    }

    function moveActive(kind, delta) {
        var box = $('mr-' + kind + '-suggest');
        if (!box || box.hidden) { return; }
        var options = box.querySelectorAll('.mr-suggest-item');
        if (!options.length) { return; }

        var next = (activeIndex[kind] === undefined ? -1 : activeIndex[kind]) + delta;
        if (next < 0) { next = options.length - 1; }
        if (next >= options.length) { next = 0; }
        activeIndex[kind] = next;

        Array.prototype.forEach.call(options, function (option, index) {
            option.classList.toggle('mr-suggest-active', index === next);
        });
        options[next].scrollIntoView({ block: 'nearest' });
    }

    function bindTokenField(kind) {
        var input = $('mr-' + kind + '-input');
        var field = $('mr-' + kind + '-field');
        var box = $('mr-' + kind + '-suggest');
        if (!input || !field) { return; }

        // Clicking anywhere in the chip area focuses the input, as a text field should.
        field.addEventListener('click', function (event) {
            if (event.target === field) { input.focus(); }
        });

        input.addEventListener('input', function () {
            window.clearTimeout(timers[kind]);
            timers[kind] = window.setTimeout(function () {
                querySuggestions(kind);
            }, DEBOUNCE_MS);
        });

        input.addEventListener('focus', function () { querySuggestions(kind); });

        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowDown') { event.preventDefault(); moveActive(kind, 1); }
            else if (event.key === 'ArrowUp') { event.preventDefault(); moveActive(kind, -1); }
            else if (event.key === 'Escape') { hideSuggestions(kind); }
            else if (event.key === 'Enter') {
                event.preventDefault();
                var active = box && box.querySelector('.mr-suggest-active');
                if (active) { active.click(); }
            } else if (event.key === 'Backspace' && input.value === ''
                       && selection[kind].length) {
                // Backspace on an empty input removes the last chip - standard for this widget.
                removeToken(kind, selection[kind][selection[kind].length - 1]);
            }
        });

        document.addEventListener('click', function (event) {
            if (!field.contains(event.target) && (!box || !box.contains(event.target))) {
                hideSuggestions(kind);
            }
        });
    }

    // ---------------------------------------------------------------
    // search
    // ---------------------------------------------------------------

    function clearFilters() {
        selection.author = [];
        selection.image = [];
        renderTokens('author');
        renderTokens('image');
        var mine = $('mr-mine-only');
        if (mine) { mine.checked = false; }
        search();
    }

    function search() {
        clearNotice();
        var button = $('mr-search');
        if (button) { button.disabled = true; }

        var mine = $('mr-mine-only') && $('mr-mine-only').checked;
        var params = [];
        // "mine" is resolved server-side from the session, so no author id is sent for it.
        if (!mine && selection.author.length) {
            params.push('authorIds=' + encodeURIComponent(
                selection.author.map(function (a) { return a.id; }).join(',')));
        }
        if (selection.image.length) {
            params.push('studyUids=' + encodeURIComponent(
                selection.image.map(function (i) { return i.studyUid; }).join(',')));
        }
        if (mine) { params.push('mine=true'); }

        var host = $('mr-results');
        if (host) {
            host.innerHTML = '';
            host.appendChild(el('p', 'mr-empty', m('searching')));
        }

        get(cfg.base + '/reportSearch.form?' + params.join('&'))
            .then(function (body) { renderResults(body.reports || []); })
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

        var count = $('mr-kpi-count');
        if (count) { count.textContent = String(reports.length); }
        var title = $('mr-results-title');
        if (title) { title.textContent = reports.length + ' ' + m('results'); }

        if (!reports.length) {
            host.appendChild(el('p', 'mr-empty', m('none')));
            return;
        }
        reports.forEach(function (report) {
            host.appendChild(renderReport(report));
        });
    }

    /**
     * One report card, in three visually distinct tiers: title, a labelled metadata strip,
     * and the clinical text in its own panel. Previously all three were the same muted text,
     * which is what made the list unreadable.
     */
    function renderReport(report) {
        var current = report.current || {};
        var patient = report.patient || {};

        var card = el('article', 'mr-report'
            + (report.isOwn ? ' mr-own' : '')
            + (report.voided ? ' mr-removed' : ''));

        var head = el('div', 'mr-report-head');
        head.appendChild(el('h3', 'mr-report-title', current.title || m('untitled')));
        if (report.isOwn) { head.appendChild(el('span', 'mr-tag mr-tag-own', m('own'))); }
        if (report.voided) { head.appendChild(el('span', 'mr-tag mr-tag-removed', m('removed'))); }
        card.appendChild(head);

        var meta = el('dl', 'mr-report-meta');
        var name = [patient.familyName, patient.givenName].filter(Boolean).join(' ');
        meta.appendChild(metaEntry(m('patient'), name || '-', patient.identifier));
        meta.appendChild(metaEntry(m('author'), report.author || '-'));
        meta.appendChild(metaEntry(m('date'), current.dateCreated || '-'));
        if (current.versionNumber) {
            meta.appendChild(metaEntry(m('version'), String(current.versionNumber)));
        }
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

    function metaEntry(label, value, identifier) {
        var row = el('div');
        row.appendChild(el('dt', null, label));
        var dd = el('dd', null, value);
        if (identifier) {
            dd.appendChild(el('span', 'mr-ident', identifier));
        }
        row.appendChild(dd);
        return row;
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
        // image picker and the full editor. Duplicating it here would mean two editors to
        // keep in step, so this links across instead.
        var patientPage = patient.id
            ? '/' + OPENMRS_CONTEXT_PATH + '/medreport/imagingReports.page?patientId='
              + encodeURIComponent(patient.id)
            : null;

        if (patientPage) {
            var open = el('a', 'mr-btn mr-btn-small', m('open'));
            open.href = patientPage;
            actions.appendChild(open);
        }

        // Disabled with a reason on someone else's report rather than hidden, so it reads as
        // "not yours" instead of a missing feature. The server enforces it regardless.
        var edit = el('button', 'mr-btn mr-btn-small', m('edit'));
        edit.type = 'button';
        if (report.canEdit && patientPage) {
            edit.addEventListener('click', function () { window.location.href = patientPage; });
        } else {
            edit.disabled = true;
            if (!report.isOwn) { edit.title = m('notOwner'); }
        }
        actions.appendChild(edit);

        return actions;
    }

    // ---------------------------------------------------------------
    // bootstrap
    // ---------------------------------------------------------------

    function init(options) {
        cfg = options || {};

        bindTokenField('author');
        bindTokenField('image');

        var searchButton = $('mr-search');
        if (searchButton) { searchButton.addEventListener('click', search); }
        var clearButton = $('mr-clear');
        if (clearButton) { clearButton.addEventListener('click', clearFilters); }
        var mine = $('mr-mine-only');
        if (mine) { mine.addEventListener('change', search); }

        // Land on something useful rather than an empty screen.
        search();
    }

    return { init: init, search: search };
}());
