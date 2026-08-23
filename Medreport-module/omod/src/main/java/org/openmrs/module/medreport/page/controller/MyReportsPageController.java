package org.openmrs.module.medreport.page.controller;

import org.openmrs.module.medreport.MedreportPrivileges;
import org.openmrs.ui.framework.page.PageModel;

/**
 * Cross-patient report search: "everything user2 wrote about studies 5 and 6".
 *
 * <p>The page itself carries no data. Both filter lists and the results come from
 * {@code reportFilters.form} / {@code reportSearch.form}, so the privilege checks that matter
 * live on the API side and there is exactly one code path producing results.
 *
 * <p>Gated on {@code medreport.imaging.view} rather than on a new privilege: RP2 already
 * grants a holder of that privilege the right to read any author's report, so being able to
 * <em>find</em> reports by author exposes nothing they could not already open. Editing and
 * removing stay author-only.
 */
public class MyReportsPageController {

    public void controller(PageModel model) {
        boolean canView = MedreportPrivileges.canViewImaging();
        model.addAttribute("accessDenied", !canView);
        model.addAttribute("canManage", MedreportPrivileges.canManageImaging());
        model.addAttribute("isAdmin", MedreportPrivileges.isReportAdmin());
    }
}
