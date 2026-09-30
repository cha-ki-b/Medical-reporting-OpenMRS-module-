<%
    ui.decorateWith("appui", "standardEmrPage", [title: ui.message("medreport.imaging.title")])
    ui.includeCss("medreport", "medreport.css")
%>

<% if (accessDenied) { %>

    <div class="mr-access-denied">
        <h2>${ ui.message("medreport.error") }</h2>
        <p>${ ui.message("medreport.accessDenied") }</p>
    </div>

<% } else { %>

<%
    // Same null/"null" guard as every other template here: Groovy renders a real null as the
    // text "null", and some legacy write paths store that literal four-character string.
    def show = { value -> (value && value.toString().trim().toLowerCase() != 'null') ? value.toString().trim() : '' }
    def familyName = show(patient.familyName)
    def givenName = show(patient.givenName)
    def identifier = patient.activeIdentifiers ? show(patient.activeIdentifiers[0].identifier) : ''
%>

<div class="mr-wrap">

    <% /*
      Which build is this? Printed, not inferred. Two independent numbers: the module
      version comes from the running module registry (server side), and " . css x.y.z"
      is appended by medreport.css itself. Seeing both, and seeing them agree, is proof
      that the .omod you uploaded is the one being served and that its stylesheet
      reached the browser. A missing suffix means the stylesheet did not load; an
      unexpected version means an older .omod is still installed alongside the new one.
    */ %>
    <p class="mr-build">medreport ${ buildStamp }</p>

    <div class="mr-header">
        <div>
            <h1>${ ui.message("medreport.imaging.title") }</h1>
            <p class="mr-sub">${ ui.message("medreport.imaging.pageSubtitle") }</p>
        </div>
        <div class="mr-patient-chip">
            <strong>${ familyName } ${ givenName }</strong><br/>
            <% if (identifier) { %><span class="mr-meta">${ identifier }</span><br/><% } %>
            <a class="mr-btn mr-btn-small" style="margin-top:.35rem"
               href="${ ui.pageLink('imaging', 'studies', [patientId: patient.patientId]) }">
                ${ ui.message("medreport.imaging.backToStudies") }
            </a>
        </div>
    </div>

    <%
        // The whole panel - list, filters, editor, history - is the same fragment the imaging
        // module used to embed. Only its host changed.
        def fragmentConfig = [
                patientId       : patient.patientId,
                availableImages : availableImages,
                studyUid        : studyUid,
                seriesUid       : seriesUid ]
    %>
    ${ ui.includeFragment("medreport", "imageReports", fragmentConfig) }

    <% if (!imagingAvailable) { %>
        <div class="mr-note mr-note-warn">
            ${ ui.message("medreport.imaging.noImagingModule") }
        </div>
    <% } %>

</div>

<% if (openEditor) { %>
<script type="text/javascript">
    // Arriving from a per-series action: open the editor immediately, already scoped to that
    // series, so writing a report about one sequence is a single click from the studies page.
    jQuery(function () {
        window.setTimeout(function () {
            if (window.medreportImaging && medreportImaging.openScoped) {
                medreportImaging.openScoped();
            }
        }, 250);
    });
</script>
<% } %>

<% } %>
