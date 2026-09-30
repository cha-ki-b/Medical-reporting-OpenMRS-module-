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

    <div class="mr-page-head">
        <div>
            <h1>${ ui.message("medreport.search.title") }</h1>
            <p class="mr-sub">${ ui.message("medreport.search.subtitle") }</p>
        </div>
        <div class="mr-page-head-actions">
            <span class="mr-kpi"><strong id="mr-kpi-count">0</strong>
                <span id="mr-kpi-label">${ ui.message("medreport.search.results") }</span></span>
        </div>
    </div>

    <div id="mr-search-notice" class="mr-note" hidden></div>

    <% /*
      Two columns, not one stacked list. Putting the filters in their own column is what
      actually separates "the controls" from "the results" - tinting a panel does not, as the
      first version of this page demonstrated.
    */ %>
    <div class="mr-search-layout">

        <aside class="mr-filters">
            <div class="mr-card">
                <div class="mr-card-head">
                    <h2>${ ui.message("medreport.search.filters") }</h2>
                    <button type="button" class="mr-link-btn" id="mr-clear">
                        ${ ui.message("medreport.search.clear") }
                    </button>
                </div>
                <div class="mr-card-body">

                    <% /*
                      Type-ahead token fields, not checkbox lists. A checkbox per author and
                      per study collapses at real scale - a PACS has thousands of studies.
                      Here the widget's size is bounded by what the user has selected, and
                      the options are queried from the server as they type.
                    */ %>
                    <div class="mr-field">
                        <label class="mr-label" for="mr-author-input">
                            ${ ui.message("medreport.search.byAuthor") }
                        </label>
                        <div class="mr-tokenfield" id="mr-author-field">
                            <input id="mr-author-input" class="mr-token-input" autocomplete="off"
                                   role="combobox" aria-expanded="false" aria-autocomplete="list"
                                   aria-controls="mr-author-suggest"
                                   placeholder="${ ui.message('medreport.search.authorPlaceholder') }"/>
                        </div>
                        <div class="mr-suggest" id="mr-author-suggest" role="listbox" hidden></div>
                    </div>

                    <div class="mr-field">
                        <label class="mr-label" for="mr-image-input">
                            ${ ui.message("medreport.search.byImage") }
                        </label>
                        <div class="mr-tokenfield" id="mr-image-field">
                            <input id="mr-image-input" class="mr-token-input" autocomplete="off"
                                   role="combobox" aria-expanded="false" aria-autocomplete="list"
                                   aria-controls="mr-image-suggest"
                                   placeholder="${ ui.message('medreport.search.imagePlaceholder') }"/>
                        </div>
                        <div class="mr-suggest" id="mr-image-suggest" role="listbox" hidden></div>
                    </div>

                    <hr class="mr-sep"/>

                    <label class="mr-switch">
                        <input type="checkbox" id="mr-mine-only"/>
                        <span class="mr-switch-track"></span>
                        <span class="mr-switch-label">${ ui.message("medreport.search.mineOnly") }</span>
                    </label>

                    <button type="button" id="mr-search" class="mr-btn mr-btn-primary mr-btn-block"
                            style="margin-top:1rem">
                        ${ ui.message("medreport.search.run") }
                    </button>
                </div>
            </div>
        </aside>

        <section class="mr-results">
            <div class="mr-results-head">
                <h2 id="mr-results-title">${ ui.message("medreport.search.results") }</h2>
                <span class="mr-meta">${ ui.message("medreport.search.sortedBy") }</span>
            </div>
            <div id="mr-results"></div>
        </section>

    </div>
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
                date: '${ ui.escapeJs(ui.message("medreport.imaging.date")) }',
                patient: '${ ui.escapeJs(ui.message("medreport.search.patient")) }',
                edit: '${ ui.escapeJs(ui.message("medreport.imaging.edit")) }',
                open: '${ ui.escapeJs(ui.message("medreport.search.open")) }',
                download: '${ ui.escapeJs(ui.message("medreport.download")) }',
                removed: '${ ui.escapeJs(ui.message("medreport.imaging.removed")) }',
                own: '${ ui.escapeJs(ui.message("medreport.imaging.own")) }',
                notOwner: '${ ui.escapeJs(ui.message("medreport.imaging.notOwner")) }',
                results: '${ ui.escapeJs(ui.message("medreport.search.results")) }',
                searching: '${ ui.escapeJs(ui.message("medreport.search.searching")) }',
                untitled: '${ ui.escapeJs(ui.message("medreport.search.untitled")) }',
                noMatch: '${ ui.escapeJs(ui.message("medreport.search.noMatch")) }',
                more: '${ ui.escapeJs(ui.message("medreport.search.more")) }',
                remove: '${ ui.escapeJs(ui.message("medreport.search.removeToken")) }'
            }
        });
    });
</script>

<% } %>
