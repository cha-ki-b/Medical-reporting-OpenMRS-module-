<%
    ui.decorateWith("appui", "standardEmrPage", [title: ui.message("medreport.search.title")])
    ui.includeCss("medreport", "medreport.css")
    ui.includeJavascript("medreport", "medreport-search.js")
%>

<% if (accessDenied) { %>

    <div class="mr-access-denied">
        <h2>${ ui.message("medreport.error") }</h2>
        <p>${ ui.message("medreport.accessDenied") }</p>
    </div>

<% } else { %>

<div class="mr-wrap">

    <div class="mr-header">
        <div>
            <h1>${ ui.message("medreport.search.title") }</h1>
            <p class="mr-sub">${ ui.message("medreport.search.subtitle") }</p>
        </div>
    </div>

    <div id="mr-search-notice" class="mr-note" hidden></div>

    <div class="mr-panel">
        <h2>${ ui.message("medreport.search.filters") }</h2>
        <div class="mr-panel-body">

            <div class="mr-filter-grid">
                <div class="mr-field">
                    <label>
                        ${ ui.message("medreport.search.byAuthor") }
                        <span class="mr-count" id="mr-author-count"></span>
                    </label>
                    <% /*
                      A checkbox list, not a single select: the requirement is a SET of users
                      intersected with a SET of images. Only authors who have actually written
                      a report appear, so the list stays short and meaningful.
                    */ %>
                    <div id="mr-author-list" class="mr-picker"></div>
                </div>

                <div class="mr-field">
                    <label>
                        ${ ui.message("medreport.search.byImage") }
                        <span class="mr-count" id="mr-image-count"></span>
                    </label>
                    <div id="mr-image-list" class="mr-picker"></div>
                </div>
            </div>

            <div class="mr-toolbar" style="margin-top:.6rem">
                <label class="mr-check mr-check-inline">
                    <input type="checkbox" id="mr-mine-only"/>
                    <span>${ ui.message("medreport.search.mineOnly") }</span>
                </label>
                <button type="button" id="mr-search" class="mr-btn mr-btn-primary">
                    ${ ui.message("medreport.search.run") }
                </button>
                <button type="button" id="mr-clear" class="mr-btn mr-btn-small">
                    ${ ui.message("medreport.search.clear") }
                </button>
                <span class="mr-meta" id="mr-result-count"></span>
            </div>

        </div>
    </div>

    <div id="mr-results"></div>

</div>

<script type="text/javascript">
    // Every message escaped: French carries apostrophes, and one of them inside a
    // single-quoted JS literal kills the whole script block (see ModuleWiringTest).
    jQuery(function () {
        medreportSearch.init({
            base: '/' + OPENMRS_CONTEXT_PATH + '/module/medreport',
            isAdmin: ${ isAdmin },
            messages: {
                none: '${ ui.escapeJs(ui.message("medreport.search.none")) }',
                author: '${ ui.escapeJs(ui.message("medreport.imaging.author")) }',
                version: '${ ui.escapeJs(ui.message("medreport.imaging.version")) }',
                patient: '${ ui.escapeJs(ui.message("medreport.search.patient")) }',
                edit: '${ ui.escapeJs(ui.message("medreport.imaging.edit")) }',
                remove: '${ ui.escapeJs(ui.message("medreport.imaging.remove")) }',
                open: '${ ui.escapeJs(ui.message("medreport.search.open")) }',
                download: '${ ui.escapeJs(ui.message("medreport.download")) }',
                removed: '${ ui.escapeJs(ui.message("medreport.imaging.removed")) }',
                own: '${ ui.escapeJs(ui.message("medreport.imaging.own")) }',
                notOwner: '${ ui.escapeJs(ui.message("medreport.imaging.notOwner")) }',
                results: '${ ui.escapeJs(ui.message("medreport.search.results")) }',
                selected: '${ ui.escapeJs(ui.message("medreport.imaging.selectedCount")) }',
                searching: '${ ui.escapeJs(ui.message("medreport.search.searching")) }'
            }
        });
    });
</script>

<% } %>
