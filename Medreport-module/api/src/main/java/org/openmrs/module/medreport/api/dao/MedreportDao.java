package org.openmrs.module.medreport.api.dao;

import org.openmrs.Patient;
import org.openmrs.User;
import org.openmrs.module.medreport.api.model.ImageReport;
import org.openmrs.module.medreport.api.model.ImageReportVersion;
import org.openmrs.module.medreport.api.model.MedreportOperationLog;
import org.openmrs.module.medreport.api.model.ReportImageLink;
import org.openmrs.module.medreport.api.model.UserReportPreference;

import java.util.List;

/**
 * Persistence for medreport.
 *
 * <p>Note what is absent: there is no delete method for a report, a version, or an audit
 * entry, anywhere in this interface. Removal is a soft delete (RP5), versions are immutable
 * (RP8), and the log is append-only (RP7) - so the operations that would violate those rules
 * are simply not expressible through the DAO.
 */
public interface MedreportDao {

    // -- reports ---------------------------------------------------------

    ImageReport saveReport(ImageReport report);

    ImageReport getReport(Integer reportId);

    ImageReport getReportByUuid(String uuid);

    /**
     * Reports covering a given Orthanc study - the reverse direction of the many-to-many
     * (RP9). Only the association rows belonging to each report's <em>current</em> version
     * count, so a study dropped by a later edit stops listing that report.
     *
     * @param includeVoided admin-only; false everywhere else so a soft-deleted report is
     *                      invisible (RP5)
     */
    List<ImageReport> getReportsForStudy(String orthancStudyUid, boolean includeVoided);

    List<ImageReport> getReportsForSeries(String orthancSeriesUid, boolean includeVoided);

    List<ImageReport> getReportsForPatient(Patient patient, boolean includeVoided);

    /**
     * Cross-patient search: reports whose author is in {@code authorIds} AND whose current
     * version covers at least one study in {@code studyUids}. Either list may be null or
     * empty, meaning "no constraint on that axis" - so the two filters compose, which is what
     * makes "everything user2 wrote about studies 5 and 6" a single query.
     *
     * <p>Ordered newest first.
     */
    List<ImageReport> searchReports(List<Integer> authorIds, List<String> studyUids,
                                    boolean includeVoided, int limit);

    /** Authors who have actually written a report - the only useful contents of an author filter. */
    List<User> getDistinctAuthors(boolean includeVoided);

    /**
     * Images that at least one report covers, newest report first. Populates the image filter
     * with exactly the studies worth filtering on, rather than every study in Orthanc.
     */
    List<ReportImageLink> getDistinctReportedImages(boolean includeVoided);

    // -- versions --------------------------------------------------------

    ImageReportVersion saveVersion(ImageReportVersion version);

    ImageReportVersion getVersion(Integer versionId);

    ImageReportVersion getVersionByUuid(String uuid);

    /** Full chain, oldest first. Admin-only at the service layer (RP4). */
    List<ImageReportVersion> getVersions(ImageReport report);

    ImageReportVersion getCurrentVersion(ImageReport report);

    /**
     * Clear {@code is_current} on every version of a report. Called immediately before the
     * new version is flagged current, so exactly one row ever carries the flag (RP8).
     */
    void clearCurrentFlag(ImageReport report);

    int getNextVersionNumber(ImageReport report);

    // -- audit -----------------------------------------------------------

    MedreportOperationLog saveLog(MedreportOperationLog entry);

    List<MedreportOperationLog> getLogsForReport(Integer reportId);

    List<MedreportOperationLog> getRecentLogs(int limit);

    // -- preferences -----------------------------------------------------

    UserReportPreference getPreference(User user, String key);

    UserReportPreference savePreference(UserReportPreference preference);
}
