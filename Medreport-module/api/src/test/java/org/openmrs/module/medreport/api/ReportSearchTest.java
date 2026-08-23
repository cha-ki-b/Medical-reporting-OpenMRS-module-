package org.openmrs.module.medreport.api;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;
import org.mockito.Mockito;
import org.openmrs.User;
import org.openmrs.api.APIAuthenticationException;
import org.openmrs.api.context.Context;
import org.openmrs.module.medreport.MedreportPrivileges;
import org.openmrs.module.medreport.api.dao.MedreportDao;
import org.openmrs.module.medreport.api.impl.ImageReportServiceImpl;
import org.openmrs.module.medreport.api.model.ImageReport;
import org.openmrs.module.medreport.api.render.ReportRenderClient;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Cross-patient search: "everything user2 wrote about studies 5 and 6".
 *
 * <p>The two filters are independent sets that intersect, so the tests below check that each
 * axis is passed through as given and that an empty axis means "no constraint" rather than
 * "match nothing" - the difference between a useful default view and a blank screen.
 */
public class ReportSearchTest {

    private MedreportDao dao;

    private ImageReportServiceImpl service;

    private MockedStatic<Context> context;

    private User user;

    @Before
    public void setUp() {
        dao = mock(MedreportDao.class);
        service = new ImageReportServiceImpl();
        service.setDao(dao);
        service.setAuditService(mock(MedreportAuditService.class));
        service.setRenderClient(mock(ReportRenderClient.class));

        user = new User();
        user.setUserId(7);
        user.setUsername("dr.kaci");

        context = Mockito.mockStatic(Context.class);
        context.when(Context::getAuthenticatedUser).thenReturn(user);
        when(dao.searchReports(anyList(), anyList(), anyBoolean(), anyInt()))
                .thenReturn(Collections.<ImageReport>emptyList());
    }

    @After
    public void tearDown() {
        context.close();
    }

    private void loginWith(String... privileges) {
        context.when(() -> Context.hasPrivilege(anyString())).thenReturn(false);
        for (String privilege : privileges) {
            context.when(() -> Context.hasPrivilege(privilege)).thenReturn(true);
        }
    }

    @Test
    public void searchRequiresTheViewPrivilege() {
        loginWith(MedreportPrivileges.APP_IMAGING_MANAGE);
        try {
            service.searchReports(null, null, 50);
            fail("expected the search to be refused");
        } catch (APIAuthenticationException expected) {
            assertTrue(expected.getMessage().contains(MedreportPrivileges.APP_IMAGING_VIEW));
        }
    }

    @Test
    public void bothFilterAxesArePassedThroughTogether() {
        loginWith(MedreportPrivileges.APP_IMAGING_VIEW);

        service.searchReports(Arrays.asList(2, 3), Arrays.asList("study-5", "study-6"), 50);

        ArgumentCaptor<List> authors = ArgumentCaptor.forClass(List.class);
        ArgumentCaptor<List> studies = ArgumentCaptor.forClass(List.class);
        verify(dao).searchReports(authors.capture(), studies.capture(), anyBoolean(), anyInt());

        assertEquals(Arrays.asList(2, 3), authors.getValue());
        assertEquals(Arrays.asList("study-5", "study-6"), studies.getValue());
    }

    @Test
    public void anEmptyAxisMeansNoConstraintNotNoResults() {
        loginWith(MedreportPrivileges.APP_IMAGING_VIEW);

        service.searchReports(Collections.<Integer>emptyList(), Arrays.asList("study-5"), 50);

        ArgumentCaptor<List> authors = ArgumentCaptor.forClass(List.class);
        verify(dao).searchReports(authors.capture(), Mockito.anyList(), anyBoolean(), anyInt());
        assertTrue("an empty author list must reach the DAO as empty, meaning 'any author'",
                authors.getValue().isEmpty());
    }

    /** RP5: a soft-deleted report stays out of search for everyone but an administrator. */
    @Test
    public void removedReportsAreExcludedUnlessTheCallerIsAnAdministrator() {
        loginWith(MedreportPrivileges.APP_IMAGING_VIEW);
        service.searchReports(null, null, 50);
        verify(dao).searchReports(Mockito.any(), Mockito.any(), Mockito.eq(false), anyInt());

        Mockito.reset(dao);
        loginWith(MedreportPrivileges.APP_IMAGING_VIEW, MedreportPrivileges.APP_ADMIN);
        service.searchReports(null, null, 50);
        verify(dao).searchReports(Mockito.any(), Mockito.any(), Mockito.eq(true), anyInt());
    }

    @Test
    public void filterOptionsRequireTheViewPrivilege() {
        loginWith();
        try {
            service.getReportAuthors();
            fail("expected the author list to be refused");
        } catch (APIAuthenticationException expected) {
            assertTrue(expected.getMessage().contains(MedreportPrivileges.APP_IMAGING_VIEW));
        }
        try {
            service.getReportedImages();
            fail("expected the image list to be refused");
        } catch (APIAuthenticationException expected) {
            assertTrue(expected.getMessage().contains(MedreportPrivileges.APP_IMAGING_VIEW));
        }
    }

    /**
     * Searching by author needs only the read privilege, because RP2 already lets a holder
     * read any author's report - finding them exposes nothing new. This pins that decision so
     * it is not "tightened" later without a deliberate choice.
     */
    @Test
    public void searchingByAnotherAuthorNeedsOnlyTheReadPrivilege() {
        loginWith(MedreportPrivileges.APP_IMAGING_VIEW);
        service.searchReports(Arrays.asList(99), null, 50);
        verify(dao).searchReports(Mockito.any(), Mockito.any(), anyBoolean(), anyInt());
        assertFalse("no manage privilege should be required to search",
                Context.hasPrivilege(MedreportPrivileges.APP_IMAGING_MANAGE));
    }
}
