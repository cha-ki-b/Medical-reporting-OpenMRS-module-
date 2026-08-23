package org.openmrs.module.medreport.api.catalog;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.openmrs.Patient;
import org.openmrs.api.context.Context;
import org.openmrs.util.OpenmrsClassLoader;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Lists a patient's DICOM studies, so medreport's own imaging-reports page can offer an image
 * picker without the imaging module having to push the list in.
 *
 * <h3>Why reflection rather than a dependency</h3>
 * Adding {@code imaging-api} to this module's pom would make reporting unable to start without
 * the imaging module, and would invert the dependency direction the whole design rests on
 * (see the module README §4). So this resolves {@code DicomStudyService} through OpenMRS's own
 * classloader and calls it through the service registry - the same technique
 * {@link DataSourceRegistry} already uses for clinical data, and the reason {@code config.xml}
 * lists imaging as {@code aware_of_module} rather than {@code require_module}.
 *
 * <p>Going through {@code Context.getService(...)} also means the imaging module's own
 * authorization advice still runs; this is not a way around it.
 *
 * <p>Every failure mode - module absent, service missing, method renamed, Orthanc unreachable
 * - degrades to an empty list. The page then shows the "paste a study UID" escape hatch
 * instead of a picker, which is inconvenient but never broken.
 */
public class ImagingStudyLookup {

    private static final Log log = LogFactory.getLog(ImagingStudyLookup.class);

    private static final String SERVICE_CLASS = "org.openmrs.module.imaging.api.DicomStudyService";

    private static final String METHOD = "getStudiesOfPatient";

    /**
     * @return one map per study, with the keys the {@code imageReports} fragment expects
     *         ({@code studyUid}, {@code studyInstanceUid}, {@code studyDate},
     *         {@code studyDescription}); empty when imaging is unavailable.
     */
    @SuppressWarnings({ "unchecked", "rawtypes" })
    public List<Map<String, Object>> getStudiesForPatient(Patient patient) {
        if (patient == null) {
            return Collections.emptyList();
        }
        try {
            Class<?> serviceClass = OpenmrsClassLoader.getInstance().loadClass(SERVICE_CLASS);
            Object service = Context.getService((Class) serviceClass);
            if (service == null) {
                return Collections.emptyList();
            }
            Method method = serviceClass.getMethod(METHOD, Patient.class);
            Object result = method.invoke(service, patient);
            if (!(result instanceof List)) {
                return Collections.emptyList();
            }

            List<Map<String, Object>> studies = new ArrayList<Map<String, Object>>();
            for (Object study : (List<Object>) result) {
                Map<String, Object> entry = describe(study);
                if (entry != null) {
                    studies.add(entry);
                }
            }
            return studies;
        } catch (ClassNotFoundException e) {
            // The imaging module simply is not installed. Expected, not an error.
            log.debug("medreport: the imaging module is not present; no study picker.");
            return Collections.emptyList();
        } catch (Exception e) {
            log.warn("medreport: could not list DICOM studies for the report picker; "
                    + "falling back to manual study UID entry.", e);
            return Collections.emptyList();
        }
    }

    /** Read the handful of getters we need, tolerating any of them being absent. */
    private Map<String, Object> describe(Object study) {
        if (study == null) {
            return null;
        }
        String orthancUid = readString(study, "getOrthancStudyUID");
        if (orthancUid == null || orthancUid.trim().isEmpty()) {
            // Without the Orthanc UID there is nothing to key a report against.
            return null;
        }
        Map<String, Object> entry = new LinkedHashMap<String, Object>();
        entry.put("studyUid", orthancUid);
        entry.put("studyInstanceUid", readString(study, "getStudyInstanceUID"));
        entry.put("studyDate", readString(study, "getStudyDate"));
        entry.put("studyDescription", readString(study, "getStudyDescription"));
        return entry;
    }

    private String readString(Object target, String getter) {
        try {
            Object value = target.getClass().getMethod(getter).invoke(target);
            return value != null ? String.valueOf(value) : null;
        } catch (Exception e) {
            return null;
        }
    }

    /** Whether the imaging module is present at all - used to decide what to tell the user. */
    public boolean isImagingAvailable() {
        try {
            OpenmrsClassLoader.getInstance().loadClass(SERVICE_CLASS);
            return true;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }
}
