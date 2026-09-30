package org.openmrs.module.medreport.web;

import org.openmrs.module.Module;
import org.openmrs.module.ModuleFactory;

/**
 * The version of the medreport module the server is actually running.
 *
 * <p>This exists because of a deployment failure that cost several rounds of debugging. A new
 * .omod was built, verified and uploaded, yet the browser kept rendering the previous
 * release. Every local check passed - the stylesheet was valid, packaged at the right path
 * and byte-identical to source - because nothing was wrong with the artifact: the server was
 * still serving an older one. OpenMRS keys uploaded modules by filename, and each release
 * here changes the filename (medreport1.2.1.omod), so uploading without first deleting the
 * previous file can leave two .omod files of the same module id side by side.
 *
 * <p>There was no way to tell from the rendered page which one had won. Now there is: the
 * pages print this value, so "which build am I looking at" is answered by looking, not by
 * inferring it from what the CSS appears to be doing.
 *
 * <p>Reading it from {@link ModuleFactory} rather than from a build-time constant is the
 * whole point - a constant compiled into the jar would report the version of the jar it was
 * compiled into, which is exactly the thing already in doubt. This reports what the running
 * module registry says is loaded.
 */
public final class MedreportBuild {

    public static final String MODULE_ID = "medreport";

    private MedreportBuild() {
    }

    /**
     * @return the running module's version, or "?" if the registry has no such module (only
     *         reachable from a unit test, since the pages cannot render unless it is started)
     */
    public static String version() {
        Module module = ModuleFactory.getModuleById(MODULE_ID);
        return module == null || module.getVersion() == null ? "?" : module.getVersion();
    }
}
