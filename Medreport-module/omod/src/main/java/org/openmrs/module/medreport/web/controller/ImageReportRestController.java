package org.openmrs.module.medreport.web.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.openmrs.Patient;
import org.openmrs.User;
import org.openmrs.api.APIException;
import org.openmrs.api.context.Context;
import org.openmrs.module.medreport.MedreportPrivileges;
import org.openmrs.module.medreport.api.ImageReportService;
import org.openmrs.module.medreport.api.model.ImageReport;
import org.openmrs.module.medreport.api.model.ImageReportVersion;
import org.openmrs.module.medreport.api.model.ReportImageLink;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import javax.servlet.http.HttpServletRequest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Use case 1's HTTP surface - the endpoints the imaging module's tab calls.
 *
 * <p>Every handler opens with an explicit privilege check. That is not redundant with the
 * service layer's own checks: it is RP6's API half stated where a reviewer can see it, and
 * it means a mistake in one layer does not silently open the other. The UI's disabled
 * buttons are a third, purely cosmetic layer.
 *
 * <p>Note there is no endpoint that takes an author id, a "force" flag, or a version to
 * write to. Ownership and version numbering are decided by the service from the
 * authenticated user and the current state - never from the request.
 */
@Controller
public class ImageReportRestController extends MedreportBaseController {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final int MAX_OBSERVATION_LENGTH = 100000;

    private ImageReportService service() {
        return Context.getService(ImageReportService.class);
    }

    // ==================================================================
    // Read (RP2)
    // ==================================================================

    /** Reports covering the study or series currently open in the viewer. */
    @RequestMapping(value = "/module/medreport/imageReports.form", method = RequestMethod.GET)
    @ResponseBody
    public Map<String, Object> list(HttpServletRequest request,
                                    @RequestParam(value = "studyUid", required = false) String studyUid,
                                    @RequestParam(value = "seriesUid", required = false) String seriesUid,
                                    @RequestParam(value = "patientId", required = false) Integer patientId) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingView();

            List<ImageReport> reports;
            if (seriesUid != null && !seriesUid.trim().isEmpty()) {
                reports = service().getReportsForSeries(seriesUid.trim());
            } else if (studyUid != null && !studyUid.trim().isEmpty()) {
                reports = service().getReportsForStudy(studyUid.trim());
            } else if (patientId != null) {
                Patient patient = Context.getPatientService().getPatient(patientId);
                reports = patient == null
                        ? new ArrayList<ImageReport>() : service().getReportsForPatient(patient);
            } else {
                return fail("Specify a studyUid, a seriesUid or a patientId.");
            }

            List<Map<String, Object>> payload = new ArrayList<Map<String, Object>>();
            for (ImageReport report : reports) {
                payload.add(describe(report));
            }

            Map<String, Object> response = ok();
            response.put("reports", payload);
            // The UI uses these to hide or disable actions (RP6, presentation half). They
            // describe what this user may do, and are recomputed server-side every call.
            response.put("canCreate", MedreportPrivileges.canManageImaging());
            response.put("canViewHistory", service().canViewHistory());
            return response;
        } finally {
            end();
        }
    }

    /** Download the rendered document of a version. */
    @RequestMapping(value = "/module/medreport/imageReportDocument.form", method = RequestMethod.GET)
    public ResponseEntity<byte[]> document(HttpServletRequest request,
                                           @RequestParam("versionUuid") String versionUuid) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingView();
            byte[] content = service().getDocument(versionUuid);
            if (content == null) {
                return new ResponseEntity<byte[]>(HttpStatus.NOT_FOUND);
            }
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"));
            headers.set(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"compte_rendu.docx\"");
            // PHI leaving the server: keep it out of shared caches and off disk in proxies.
            headers.set(HttpHeaders.CACHE_CONTROL, "no-store, private");
            headers.set("X-Content-Type-Options", "nosniff");
            return new ResponseEntity<byte[]>(content, headers, HttpStatus.OK);
        } finally {
            end();
        }
    }

    /**
     * Cross-patient search: reports by a set of authors, about a set of images, or both.
     *
     * <p>Both parameters are comma-separated and both are optional, so the two filters
     * compose - which is what makes "everything user2 wrote about studies 5 and 6" a single
     * request rather than a client-side intersection.
     */
    @RequestMapping(value = "/module/medreport/reportSearch.form", method = RequestMethod.GET)
    @ResponseBody
    public Map<String, Object> search(HttpServletRequest request,
                                      @RequestParam(value = "authorIds", required = false) String authorIds,
                                      @RequestParam(value = "studyUids", required = false) String studyUids,
                                      @RequestParam(value = "mine", required = false,
                                              defaultValue = "false") boolean mine,
                                      @RequestParam(value = "limit", required = false,
                                              defaultValue = "200") Integer limit) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingView();

            List<Integer> authors = parseIntList(authorIds);
            if (mine) {
                // "Mine" is resolved from the session, never from a parameter - so it cannot
                // be pointed at another clinician by editing the URL.
                User current = Context.getAuthenticatedUser();
                authors = current != null && current.getUserId() != null
                        ? Collections.singletonList(current.getUserId())
                        : Collections.<Integer>emptyList();
            }

            List<ImageReport> reports = service().searchReports(
                    authors, parseStringList(studyUids), limit != null ? limit : 200);

            List<Map<String, Object>> payload = new ArrayList<Map<String, Object>>();
            for (ImageReport report : reports) {
                Map<String, Object> described = describe(report);
                // Cross-patient results are meaningless without saying whose record it is.
                described.put("patient", patientLabel(report));
                payload.add(described);
            }

            Map<String, Object> response = ok();
            response.put("reports", payload);
            response.put("canViewHistory", service().canViewHistory());
            return response;
        } finally {
            end();
        }
    }

    /**
     * Type-ahead for the filter widgets.
     *
     * <p>Replaces the previous "send every author and every image" response. That shape was
     * fine for a demo and unusable in production: a PACS holds thousands of studies, and the
     * client cannot render a checkbox per study. The filters now query as the user types, so
     * the payload is bounded by {@code limit} rather than by the catalogue.
     *
     * @param kind    {@code authors} or {@code images}; omitted returns both (first page)
     * @param q       free-text query; blank returns the most recent entries
     */
    @RequestMapping(value = "/module/medreport/filterSearch.form", method = RequestMethod.GET)
    @ResponseBody
    public Map<String, Object> filterSearch(HttpServletRequest request,
                                            @RequestParam(value = "kind", required = false) String kind,
                                            @RequestParam(value = "q", required = false) String q,
                                            @RequestParam(value = "limit", required = false,
                                                    defaultValue = "15") Integer limit) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingView();
            int capped = limit == null || limit < 1 || limit > 50 ? 15 : limit;

            Map<String, Object> response = ok();
            if (kind == null || "authors".equals(kind)) {
                List<Map<String, Object>> authors = new ArrayList<Map<String, Object>>();
                for (User author : service().searchReportAuthors(q, capped)) {
                    if (author == null || author.getUserId() == null) {
                        continue;
                    }
                    Map<String, Object> entry = new LinkedHashMap<String, Object>();
                    entry.put("id", author.getUserId());
                    entry.put("label", displayName(author));
                    entry.put("username", author.getUsername());
                    authors.add(entry);
                }
                response.put("authors", authors);
            }
            if (kind == null || "images".equals(kind)) {
                List<Map<String, Object>> images = new ArrayList<Map<String, Object>>();
                for (ReportImageLink link : service().searchReportedImages(q, capped)) {
                    Map<String, Object> entry = new LinkedHashMap<String, Object>();
                    entry.put("studyUid", link.getOrthancStudyUid());
                    entry.put("label", link.getDisplayLabel());
                    images.add(entry);
                }
                response.put("images", images);
            }
            User current = Context.getAuthenticatedUser();
            response.put("currentUserId", current != null ? current.getUserId() : null);
            return response;
        } finally {
            end();
        }
    }

    /** The two filter lists, each containing only values that actually occur in reports. */
    @RequestMapping(value = "/module/medreport/reportFilters.form", method = RequestMethod.GET)
    @ResponseBody
    public Map<String, Object> filters(HttpServletRequest request) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingView();

            List<Map<String, Object>> authors = new ArrayList<Map<String, Object>>();
            for (User author : service().getReportAuthors()) {
                if (author == null || author.getUserId() == null) {
                    continue;
                }
                Map<String, Object> entry = new LinkedHashMap<String, Object>();
                entry.put("id", author.getUserId());
                entry.put("label", displayName(author));
                entry.put("username", author.getUsername());
                authors.add(entry);
            }

            List<Map<String, Object>> images = new ArrayList<Map<String, Object>>();
            for (ReportImageLink link : service().getReportedImages()) {
                Map<String, Object> entry = new LinkedHashMap<String, Object>();
                entry.put("studyUid", link.getOrthancStudyUid());
                entry.put("label", link.getDisplayLabel());
                images.add(entry);
            }

            User current = Context.getAuthenticatedUser();
            Map<String, Object> response = ok();
            response.put("authors", authors);
            response.put("images", images);
            response.put("currentUserId", current != null ? current.getUserId() : null);
            return response;
        } finally {
            end();
        }
    }

    // ==================================================================
    // Create (RP1)
    // ==================================================================

    @RequestMapping(value = "/module/medreport/imageReports.form", method = RequestMethod.POST)
    @ResponseBody
    public Map<String, Object> create(HttpServletRequest request,
                                      @RequestParam("patientId") Integer patientId,
                                      @RequestParam(value = "title", required = false) String title,
                                      @RequestParam("observationText") String observationText,
                                      @RequestParam("images") String imagesJson) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingManage();

            Patient patient = Context.getPatientService().getPatient(patientId);
            if (patient == null) {
                return fail("Patient introuvable.");
            }
            validateObservation(observationText);

            ImageReport report = service().createReport(
                    patient, title, observationText, parseImages(imagesJson));

            Map<String, Object> response = ok();
            response.put("report", describe(report));
            return response;
        } finally {
            end();
        }
    }

    // ==================================================================
    // Update (RP3)
    // ==================================================================

    @RequestMapping(value = "/module/medreport/imageReportUpdate.form", method = RequestMethod.POST)
    @ResponseBody
    public Map<String, Object> update(HttpServletRequest request,
                                      @RequestParam("reportUuid") String reportUuid,
                                      @RequestParam(value = "title", required = false) String title,
                                      @RequestParam("observationText") String observationText,
                                      @RequestParam(value = "images", required = false) String imagesJson,
                                      @RequestParam(value = "changeReason", required = false) String changeReason) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingManage();
            validateObservation(observationText);

            List<ReportImageLink> images = imagesJson != null && !imagesJson.trim().isEmpty()
                    ? parseImages(imagesJson) : null;

            ImageReport report = service().updateReport(
                    reportUuid, title, observationText, images, changeReason);

            Map<String, Object> response = ok();
            response.put("report", describe(report));
            return response;
        } finally {
            end();
        }
    }

    // ==================================================================
    // Remove (RP5)
    // ==================================================================

    @RequestMapping(value = "/module/medreport/imageReportRemove.form", method = RequestMethod.POST)
    @ResponseBody
    public Map<String, Object> remove(HttpServletRequest request,
                                      @RequestParam("reportUuid") String reportUuid,
                                      @RequestParam(value = "reason", required = false) String reason) {
        begin(request);
        try {
            MedreportPrivileges.requireImagingManage();
            service().removeReport(reportUuid, reason);
            return ok();
        } finally {
            end();
        }
    }

    // ==================================================================
    // Administrator (RP4)
    // ==================================================================

    @RequestMapping(value = "/module/medreport/imageReportHistory.form", method = RequestMethod.GET)
    @ResponseBody
    public Map<String, Object> history(HttpServletRequest request,
                                       @RequestParam("reportUuid") String reportUuid) {
        begin(request);
        try {
            // Not requireImagingView: history is a strictly higher capability. The service
            // repeats this check and audits the refusal.
            MedreportPrivileges.requireAdmin();

            List<ImageReportVersion> versions = service().getVersionHistory(reportUuid);
            List<Map<String, Object>> payload = new ArrayList<Map<String, Object>>();
            for (ImageReportVersion version : versions) {
                payload.add(describeVersion(version, true));
            }

            Map<String, Object> response = ok();
            response.put("versions", payload);
            return response;
        } finally {
            end();
        }
    }

    @RequestMapping(value = "/module/medreport/imageReportRestore.form", method = RequestMethod.POST)
    @ResponseBody
    public Map<String, Object> restore(HttpServletRequest request,
                                       @RequestParam("reportUuid") String reportUuid,
                                       @RequestParam(value = "reason", required = false) String reason) {
        begin(request);
        try {
            MedreportPrivileges.requireAdmin();
            ImageReport report = service().restoreReport(reportUuid, reason);
            Map<String, Object> response = ok();
            response.put("report", describe(report));
            return response;
        } finally {
            end();
        }
    }

    // ==================================================================
    // Serialisation
    // ==================================================================

    /**
     * Project a report for the UI. Only the current version is ever included (RP4/RP8) -
     * the version chain is reachable only through the administrator endpoint above.
     */
    private Map<String, Object> describe(ImageReport report) {
        Map<String, Object> map = new LinkedHashMap<String, Object>();
        map.put("uuid", report.getUuid());
        map.put("patientId", report.getPatient() != null
                ? report.getPatient().getPatientId() : null);
        // RP2: every report view shows its author.
        map.put("author", displayName(report.getAuthor()));
        map.put("authorUsername", report.getAuthor() != null
                ? report.getAuthor().getUsername() : null);
        map.put("dateCreated", formatDateTime(report.getDateCreated()));
        map.put("voided", report.isVoided());

        ImageReportVersion current = report.getCurrentVersion();
        map.put("current", current != null ? describeVersion(current, false) : null);

        // Per-report capabilities, recomputed for this user on every response so a stale
        // page cannot show an Edit button that the server would refuse.
        map.put("canEdit", service().canEdit(report));
        map.put("canRemove", service().canRemove(report));
        map.put("isOwn", report.isAuthoredBy(Context.getAuthenticatedUser()));
        return map;
    }

    private Map<String, Object> describeVersion(ImageReportVersion version, boolean includeChain) {
        Map<String, Object> map = new LinkedHashMap<String, Object>();
        map.put("uuid", version.getUuid());
        map.put("versionNumber", version.getVersionNumber());
        map.put("title", version.getTitle());
        map.put("observationText", version.getObservationText());
        map.put("changeType", version.getChangeType());
        map.put("dateCreated", formatDateTime(version.getDateCreated()));
        map.put("createdBy", displayName(version.getCreatedBy()));
        map.put("current", version.isCurrent());
        map.put("hasDocument", version.getDocumentObs() != null);

        List<Map<String, Object>> images = new ArrayList<Map<String, Object>>();
        for (ReportImageLink link : version.getImages()) {
            Map<String, Object> image = new LinkedHashMap<String, Object>();
            image.put("studyUid", link.getOrthancStudyUid());
            image.put("seriesUid", link.getOrthancSeriesUid());
            image.put("studyInstanceUid", link.getStudyInstanceUid());
            image.put("modality", link.getModality());
            image.put("studyDate", link.getStudyDate());
            image.put("studyDescription", link.getStudyDescription());
            image.put("label", link.getDisplayLabel());
            images.add(image);
        }
        map.put("images", images);

        if (includeChain) {
            map.put("changeReason", version.getChangeReason());
            map.put("previousVersion", version.getPreviousVersion() != null
                    ? version.getPreviousVersion().getVersionNumber() : null);
        }
        return map;
    }

    // ==================================================================
    // Input handling
    // ==================================================================

    private void validateObservation(String text) {
        if (text == null || text.trim().isEmpty()) {
            throw new APIException("L'observation ne peut pas être vide.");
        }
        if (text.length() > MAX_OBSERVATION_LENGTH) {
            throw new APIException("L'observation dépasse la longueur maximale autorisée.");
        }
    }

    /**
     * Parse the images array the tab sends.
     *
     * <p>Accepts either a JSON array of objects or of bare UID strings, since the imaging
     * tab knows the full DICOM metadata but a caller working from a viewer URL may only have
     * the study UID. Unparseable input is rejected outright rather than partially applied -
     * a report silently covering fewer images than the author selected would be worse than
     * an error.
     */
    private List<ReportImageLink> parseImages(String json) {
        List<ReportImageLink> images = new ArrayList<ReportImageLink>();
        if (json == null || json.trim().isEmpty()) {
            throw new APIException("Sélectionnez au moins une étude ou une série.");
        }
        JsonNode root;
        try {
            root = MAPPER.readTree(json);
        } catch (Exception e) {
            throw new APIException("La liste d'images est illisible.", e);
        }
        if (!root.isArray()) {
            throw new APIException("La liste d'images doit être un tableau JSON.");
        }
        for (JsonNode node : root) {
            ReportImageLink link = new ReportImageLink();
            if (node.isTextual()) {
                link.setOrthancStudyUid(node.asText());
            } else {
                link.setOrthancStudyUid(text(node, "studyUid"));
                link.setOrthancSeriesUid(text(node, "seriesUid"));
                link.setStudyInstanceUid(text(node, "studyInstanceUid"));
                link.setModality(text(node, "modality"));
                link.setStudyDate(text(node, "studyDate"));
                link.setStudyDescription(text(node, "studyDescription"));
            }
            if (link.getOrthancStudyUid() != null && !link.getOrthancStudyUid().trim().isEmpty()) {
                images.add(link);
            }
        }
        if (images.isEmpty()) {
            throw new APIException("Sélectionnez au moins une étude ou une série.");
        }
        return images;
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        String raw = value.asText();
        if (raw == null || raw.trim().isEmpty()) {
            return null;
        }
        // Column widths are 255; truncate rather than let Hibernate fail the whole save.
        return raw.length() > 255 ? raw.substring(0, 255) : raw;
    }

    /** Comma-separated ids; anything non-numeric is dropped rather than failing the request. */
    private List<Integer> parseIntList(String raw) {
        List<Integer> values = new ArrayList<Integer>();
        if (raw == null || raw.trim().isEmpty()) {
            return values;
        }
        for (String part : raw.split(",")) {
            try {
                values.add(Integer.valueOf(part.trim()));
            } catch (NumberFormatException ignored) {
                // A malformed id narrows nothing; silently skipping it is safer than
                // failing a search the clinician can still usefully run.
            }
        }
        return values;
    }

    private List<String> parseStringList(String raw) {
        List<String> values = new ArrayList<String>();
        if (raw == null || raw.trim().isEmpty()) {
            return values;
        }
        for (String part : raw.split(",")) {
            String trimmed = part.trim();
            if (!trimmed.isEmpty() && trimmed.length() <= 255) {
                values.add(trimmed);
            }
        }
        return values;
    }

    /** Patient identity for a cross-patient result row. */
    private Map<String, Object> patientLabel(ImageReport report) {
        Map<String, Object> label = new LinkedHashMap<String, Object>();
        Patient patient = report.getPatient();
        if (patient == null) {
            return label;
        }
        label.put("id", patient.getPatientId());
        label.put("uuid", patient.getUuid());
        label.put("familyName", patient.getFamilyName());
        label.put("givenName", patient.getGivenName());
        label.put("identifier", patient.getPatientIdentifier() != null
                ? patient.getPatientIdentifier().getIdentifier() : null);
        return label;
    }

    private static String displayName(User user) {
        if (user == null) {
            return "";
        }
        if (user.getPersonName() != null) {
            String name = user.getPersonName().getFullName();
            if (name != null && !name.trim().isEmpty()) {
                return name;
            }
        }
        return user.getUsername() != null ? user.getUsername() : user.getSystemId();
    }

    private static String formatDateTime(Date date) {
        return date == null ? null : new SimpleDateFormat("dd/MM/yyyy HH:mm").format(date);
    }
}
