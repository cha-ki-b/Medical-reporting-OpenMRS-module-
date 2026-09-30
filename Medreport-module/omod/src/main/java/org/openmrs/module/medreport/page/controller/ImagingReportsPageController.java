package org.openmrs.module.medreport.page.controller;

import org.openmrs.module.medreport.web.MedreportBuild;
import org.openmrs.Patient;
import org.openmrs.api.context.Context;
import org.openmrs.module.medreport.MedreportPrivileges;
import org.openmrs.module.medreport.api.catalog.ImagingStudyLookup;
import org.openmrs.ui.framework.page.PageModel;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Standalone page for a patient's imaging reports.
 *
 * <p>This exists because embedding the panel at the bottom of the imaging module's studies
 * page was poor UX in two concrete ways: it sat below a long table where clinicians never
 * scrolled to it, and it vanished entirely on the "Get studies" navigation. A page of its
 * own, reached from a link placed *above* the studies table, fixes both - and gives the
 * per-series "write a report" action somewhere stable to point at.
 *
 * <p>The image picker is populated through {@link ImagingStudyLookup}, which reaches the
 * imaging module reflectively so this module still has no dependency on it.
 */
public class ImagingReportsPageController {

    public void controller(PageModel model,
                           @RequestParam("patientId") String patientId,
                           @RequestParam(value = "studyUid", required = false) String studyUid,
                           @RequestParam(value = "seriesUid", required = false) String seriesUid,
                           @RequestParam(value = "new", required = false) String openEditor) {
        // Printed on the page so the running build is visible without guessing (see MedreportBuild).
        model.addAttribute("buildStamp", MedreportBuild.version());

        Patient patient = resolvePatient(patientId);
        model.addAttribute("patient", patient);

        if (patient == null || !MedreportPrivileges.canViewImaging()) {
            model.addAttribute("accessDenied", true);
            model.addAttribute("availableImages", Collections.emptyList());
            model.addAttribute("studyUid", "");
            model.addAttribute("seriesUid", "");
            model.addAttribute("openEditor", false);
            model.addAttribute("imagingAvailable", false);
            return;
        }
        model.addAttribute("accessDenied", false);

        ImagingStudyLookup lookup = new ImagingStudyLookup();
        List<Map<String, Object>> studies = lookup.getStudiesForPatient(patient);
        model.addAttribute("availableImages", studies);
        model.addAttribute("imagingAvailable", lookup.isImagingAvailable());

        // Scope is a convenience for arriving from a specific study or series; the page is
        // still the patient's whole set of reports, filterable on screen.
        model.addAttribute("studyUid", studyUid != null ? studyUid : "");
        model.addAttribute("seriesUid", seriesUid != null ? seriesUid : "");
        // ?new=1 opens the editor straight away - what the per-series action links to.
        model.addAttribute("openEditor", openEditor != null && !openEditor.isEmpty());
    }

    /** Accepts either a uuid or a numeric id, since callers legitimately hold either. */
    private Patient resolvePatient(String patientId) {
        if (patientId == null || patientId.trim().isEmpty()) {
            return null;
        }
        String value = patientId.trim();
        try {
            return Context.getPatientService().getPatient(Integer.valueOf(value));
        } catch (NumberFormatException notAnId) {
            return Context.getPatientService().getPatientByUuid(value);
        }
    }
}
