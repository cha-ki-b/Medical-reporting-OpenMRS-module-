package org.openmrs.module.medreport.api.dao;

import org.hibernate.SessionFactory;
import org.openmrs.Patient;
import org.openmrs.User;
import org.openmrs.module.medreport.api.model.ImageReport;
import org.openmrs.module.medreport.api.model.ImageReportVersion;
import org.openmrs.module.medreport.api.model.MedreportOperationLog;
import org.openmrs.module.medreport.api.model.ReportImageLink;
import org.openmrs.module.medreport.api.model.UserReportPreference;

import java.util.List;

public class MedreportDaoImpl implements MedreportDao {

    private SessionFactory sessionFactory;

    public void setSessionFactory(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    // -- reports ---------------------------------------------------------

    public ImageReport saveReport(ImageReport report) {
        sessionFactory.getCurrentSession().saveOrUpdate(report);
        return report;
    }

    public ImageReport getReport(Integer reportId) {
        if (reportId == null) {
            return null;
        }
        return sessionFactory.getCurrentSession().get(ImageReport.class, reportId);
    }

    public ImageReport getReportByUuid(String uuid) {
        if (uuid == null || uuid.trim().isEmpty()) {
            return null;
        }
        return sessionFactory.getCurrentSession()
                .createQuery("from ImageReport r where r.uuid = :uuid", ImageReport.class)
                .setParameter("uuid", uuid)
                .uniqueResult();
    }

    public List<ImageReport> getReportsForStudy(String orthancStudyUid, boolean includeVoided) {
        return getReportsForImage("orthancStudyUid", orthancStudyUid, includeVoided);
    }

    public List<ImageReport> getReportsForSeries(String orthancSeriesUid, boolean includeVoided) {
        return getReportsForImage("orthancSeriesUid", orthancSeriesUid, includeVoided);
    }

    /**
     * Walks the association table, not the report table: this is the "which reports cover
     * this image" half of the many-to-many (RP9). Restricted to links owned by each report's
     * current version so an image removed by a later edit no longer surfaces that report.
     */
    private List<ImageReport> getReportsForImage(String property, String uid, boolean includeVoided) {
        if (uid == null || uid.trim().isEmpty()) {
            return java.util.Collections.emptyList();
        }
        StringBuilder hql = new StringBuilder()
                .append("select distinct link.report from ReportImageLink link ")
                .append("where link.").append(property).append(" = :uid ")
                .append("and link.version.current = true ");
        if (!includeVoided) {
            hql.append("and link.report.voided = false ");
        }
        hql.append("order by link.report.dateCreated desc");

        return sessionFactory.getCurrentSession()
                .createQuery(hql.toString(), ImageReport.class)
                .setParameter("uid", uid)
                .list();
    }

    public List<ImageReport> getReportsForPatient(Patient patient, boolean includeVoided) {
        if (patient == null) {
            return java.util.Collections.emptyList();
        }
        String hql = "from ImageReport r where r.patient = :patient "
                + (includeVoided ? "" : "and r.voided = false ")
                + "order by r.dateCreated desc";
        return sessionFactory.getCurrentSession()
                .createQuery(hql, ImageReport.class)
                .setParameter("patient", patient)
                .list();
    }

    /**
     * The filters are appended only when non-empty, so an unconstrained axis costs nothing in
     * the generated SQL. Values are always bound as parameters - never concatenated - so a
     * study UID coming from a query string cannot alter the statement.
     */
    public List<ImageReport> searchReports(List<Integer> authorIds, List<String> studyUids,
                                           boolean includeVoided, int limit) {
        boolean byAuthor = authorIds != null && !authorIds.isEmpty();
        boolean byImage = studyUids != null && !studyUids.isEmpty();

        StringBuilder hql = new StringBuilder("select distinct r from ImageReport r where 1 = 1 ");
        if (!includeVoided) {
            hql.append("and r.voided = false ");
        }
        if (byAuthor) {
            hql.append("and r.author.userId in (:authorIds) ");
        }
        if (byImage) {
            // Correlated on the CURRENT version: a study dropped by a later edit should stop
            // matching, exactly as it already does for the per-study listing.
            hql.append("and exists (select 1 from ReportImageLink l ")
               .append("where l.report = r and l.version.current = true ")
               .append("and l.orthancStudyUid in (:studyUids)) ");
        }
        hql.append("order by r.dateCreated desc");

        org.hibernate.query.Query<ImageReport> query = sessionFactory.getCurrentSession()
                .createQuery(hql.toString(), ImageReport.class);
        if (byAuthor) {
            query.setParameterList("authorIds", authorIds);
        }
        if (byImage) {
            query.setParameterList("studyUids", studyUids);
        }
        query.setMaxResults(limit > 0 ? limit : 200);
        return query.list();
    }

    public List<User> getDistinctAuthors(boolean includeVoided) {
        String hql = "select distinct r.author from ImageReport r "
                + (includeVoided ? "" : "where r.voided = false ")
                + "order by r.author.username asc";
        return sessionFactory.getCurrentSession().createQuery(hql, User.class).list();
    }

    public List<ReportImageLink> getDistinctReportedImages(boolean includeVoided) {
        // One row per distinct study UID. Grouping in HQL and re-reading the entity would need
        // a second round trip, so the de-duplication happens here on an already-small list.
        String hql = "from ReportImageLink l where l.version.current = true "
                + (includeVoided ? "" : "and l.report.voided = false ")
                + "order by l.report.dateCreated desc";
        List<ReportImageLink> all = sessionFactory.getCurrentSession()
                .createQuery(hql, ReportImageLink.class).list();

        java.util.Set<String> seen = new java.util.HashSet<String>();
        List<ReportImageLink> distinct = new java.util.ArrayList<ReportImageLink>();
        for (ReportImageLink link : all) {
            if (seen.add(link.getOrthancStudyUid())) {
                distinct.add(link);
            }
        }
        return distinct;
    }

    public List<ReportImageLink> searchReportedImages(String query, boolean includeVoided,
                                                     int limit) {
        StringBuilder hql = new StringBuilder("from ReportImageLink l where l.version.current = true ");
        if (!includeVoided) {
            hql.append("and l.report.voided = false ");
        }
        boolean filtered = query != null && !query.trim().isEmpty();
        if (filtered) {
            // Bound as a parameter, never concatenated: this string comes straight from a
            // query parameter typed by the user.
            hql.append("and (lower(l.modality) like :q or lower(l.studyDescription) like :q ")
               .append("or lower(l.studyDate) like :q or lower(l.orthancStudyUid) like :q) ");
        }
        hql.append("order by l.report.dateCreated desc");

        org.hibernate.query.Query<ReportImageLink> jpql = sessionFactory.getCurrentSession()
                .createQuery(hql.toString(), ReportImageLink.class);
        if (filtered) {
            jpql.setParameter("q", "%" + query.trim().toLowerCase() + "%");
        }
        // Over-fetch before de-duplicating: several links can share one study UID, so the
        // page size is only reached after collapsing them.
        jpql.setMaxResults(Math.max(limit, 1) * 8);

        java.util.Set<String> seen = new java.util.HashSet<String>();
        List<ReportImageLink> distinct = new java.util.ArrayList<ReportImageLink>();
        for (ReportImageLink link : jpql.list()) {
            if (seen.add(link.getOrthancStudyUid())) {
                distinct.add(link);
                if (distinct.size() >= limit) {
                    break;
                }
            }
        }
        return distinct;
    }

    // -- versions --------------------------------------------------------

    public ImageReportVersion saveVersion(ImageReportVersion version) {
        sessionFactory.getCurrentSession().saveOrUpdate(version);
        return version;
    }

    public ImageReportVersion getVersion(Integer versionId) {
        if (versionId == null) {
            return null;
        }
        return sessionFactory.getCurrentSession().get(ImageReportVersion.class, versionId);
    }

    public ImageReportVersion getVersionByUuid(String uuid) {
        if (uuid == null || uuid.trim().isEmpty()) {
            return null;
        }
        return sessionFactory.getCurrentSession()
                .createQuery("from ImageReportVersion v where v.uuid = :uuid", ImageReportVersion.class)
                .setParameter("uuid", uuid)
                .uniqueResult();
    }

    public List<ImageReportVersion> getVersions(ImageReport report) {
        if (report == null) {
            return java.util.Collections.emptyList();
        }
        return sessionFactory.getCurrentSession()
                .createQuery("from ImageReportVersion v where v.report = :report "
                        + "order by v.versionNumber asc", ImageReportVersion.class)
                .setParameter("report", report)
                .list();
    }

    public ImageReportVersion getCurrentVersion(ImageReport report) {
        if (report == null) {
            return null;
        }
        List<ImageReportVersion> results = sessionFactory.getCurrentSession()
                .createQuery("from ImageReportVersion v where v.report = :report "
                        + "and v.current = true order by v.versionNumber desc", ImageReportVersion.class)
                .setParameter("report", report)
                .setMaxResults(1)
                .list();
        return results.isEmpty() ? null : results.get(0);
    }

    public void clearCurrentFlag(ImageReport report) {
        if (report == null || report.getId() == null) {
            return;
        }
        sessionFactory.getCurrentSession()
                .createQuery("update ImageReportVersion v set v.current = false "
                        + "where v.report.id = :reportId and v.current = true")
                .setParameter("reportId", report.getId())
                .executeUpdate();
    }

    public int getNextVersionNumber(ImageReport report) {
        if (report == null || report.getId() == null) {
            return 1;
        }
        Number max = (Number) sessionFactory.getCurrentSession()
                .createQuery("select max(v.versionNumber) from ImageReportVersion v "
                        + "where v.report.id = :reportId")
                .setParameter("reportId", report.getId())
                .uniqueResult();
        return max == null ? 1 : max.intValue() + 1;
    }

    // -- audit -----------------------------------------------------------

    public MedreportOperationLog saveLog(MedreportOperationLog entry) {
        // save(), never saveOrUpdate(): an audit row is inserted once and never revised.
        sessionFactory.getCurrentSession().save(entry);
        return entry;
    }

    public List<MedreportOperationLog> getLogsForReport(Integer reportId) {
        if (reportId == null) {
            return java.util.Collections.emptyList();
        }
        return sessionFactory.getCurrentSession()
                .createQuery("from MedreportOperationLog l where l.reportId = :reportId "
                        + "order by l.dateCreated desc", MedreportOperationLog.class)
                .setParameter("reportId", reportId)
                .list();
    }

    public List<MedreportOperationLog> getRecentLogs(int limit) {
        return sessionFactory.getCurrentSession()
                .createQuery("from MedreportOperationLog l order by l.dateCreated desc",
                        MedreportOperationLog.class)
                .setMaxResults(limit > 0 ? limit : 100)
                .list();
    }

    // -- preferences -----------------------------------------------------

    public UserReportPreference getPreference(User user, String key) {
        if (user == null || key == null) {
            return null;
        }
        List<UserReportPreference> results = sessionFactory.getCurrentSession()
                .createQuery("from UserReportPreference p where p.user = :user "
                        + "and p.preferenceKey = :key", UserReportPreference.class)
                .setParameter("user", user)
                .setParameter("key", key)
                .setMaxResults(1)
                .list();
        return results.isEmpty() ? null : results.get(0);
    }

    public UserReportPreference savePreference(UserReportPreference preference) {
        sessionFactory.getCurrentSession().saveOrUpdate(preference);
        return preference;
    }
}
