package org.openmrs.module.medreport.api;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.MockedStatic;
import org.mockito.Mockito;
import org.openmrs.Patient;
import org.openmrs.PersonName;
import org.openmrs.User;
import org.openmrs.api.AdministrationService;
import org.openmrs.api.context.Context;
import org.openmrs.module.medreport.MedreportPrivileges;
import org.openmrs.module.medreport.api.catalog.DataSourceRegistry;
import org.openmrs.module.medreport.api.dao.MedreportDao;
import org.openmrs.module.medreport.api.impl.PatientReportServiceImpl;
import org.openmrs.module.medreport.api.model.UserReportPreference;
import org.openmrs.module.medreport.api.render.DocumentContext;
import org.openmrs.module.medreport.api.render.RenderedDocument;
import org.openmrs.module.medreport.api.render.ReportRenderClient;
import org.openmrs.module.medreport.api.report.ReportRequest;

import java.util.Collections;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * The doctor's free-text observation.
 *
 * <p>The interesting property is not that it reaches the document - it is that it is
 * <em>never</em> persisted as a preference. A saved observation would silently reappear,
 * pre-filled, on the next patient's report. That is a clinical-safety problem rather than a
 * convenience, so it is stripped server-side where no UI mistake can reintroduce it.
 */
public class DoctorObservationTest {

    private MedreportDao dao;

    private ReportRenderClient renderClient;

    private PatientReportServiceImpl service;

    private MockedStatic<Context> context;

    private Patient patient;

    @Before
    public void setUp() {
        dao = mock(MedreportDao.class);
        renderClient = mock(ReportRenderClient.class);
        DataSourceRegistry registry = mock(DataSourceRegistry.class);

        service = new PatientReportServiceImpl();
        service.setDao(dao);
        service.setRegistry(registry);
        service.setRenderClient(renderClient);
        service.setAuditService(mock(MedreportAuditService.class));
        service.setImageReportService(mock(ImageReportService.class));

        when(registry.getDescriptors()).thenReturn(Collections.emptyList());

        patient = new Patient();
        patient.setPatientId(11);
        patient.addName(new PersonName("Yacine", null, "BENALI"));

        context = Mockito.mockStatic(Context.class);

        AdministrationService admin = mock(AdministrationService.class);
        when(admin.getGlobalProperty(anyString(), anyString()))
                .thenAnswer(invocation -> invocation.getArgument(1));
        context.when(Context::getAdministrationService).thenReturn(admin);

        User user = new User();
        user.setUserId(3);
        user.setUsername("dr.kaci");
        context.when(Context::getAuthenticatedUser).thenReturn(user);
        context.when(() -> Context.hasPrivilege(anyString())).thenReturn(false);
        context.when(() -> Context.hasPrivilege(MedreportPrivileges.APP_DASHBOARD_GENERATE))
                .thenReturn(true);

        RenderedDocument rendered = new RenderedDocument();
        rendered.setArtifactId("0123456789abcdef0123456789abcdef");
        rendered.setFormat("pdf");
        when(renderClient.render(any(), anyString(), anyString(), anyBoolean(), anyString()))
                .thenReturn(rendered);
    }

    @After
    public void tearDown() {
        context.close();
    }

    private DocumentContext captureDocument() {
        ArgumentCaptor<DocumentContext> captor = ArgumentCaptor.forClass(DocumentContext.class);
        Mockito.verify(renderClient)
                .render(captor.capture(), anyString(), anyString(), anyBoolean(), anyString());
        return captor.getValue();
    }

    @Test
    public void theObservationReachesTheDocumentVerbatim() {
        ReportRequest request = new ReportRequest();
        request.setDoctorObservation("Patient stable.\nRevoir dans 3 mois.");

        service.generate(patient, request);

        assertEquals("Patient stable.\nRevoir dans 3 mois.",
                captureDocument().getDoctorObservation());
    }

    @Test
    public void aBlankObservationBecomesNullRatherThanAnEmptyHeading() {
        ReportRequest request = new ReportRequest();
        request.setDoctorObservation("   \n  ");

        service.generate(patient, request);

        assertNull(captureDocument().getDoctorObservation());
    }

    @Test
    public void noObservationIsFine() {
        service.generate(patient, new ReportRequest());
        assertNull(captureDocument().getDoctorObservation());
    }

    /** The safety property: it must not survive into the saved preference. */
    @Test
    public void theObservationIsStrippedBeforePreferencesArePersisted() {
        ReportRequest request = new ReportRequest();
        request.setDoctorObservation("Suspicion de recidive - NE PAS REUTILISER");
        request.setLanguage("en");
        request.setFormat("docx");

        service.savePreferences(request);

        ArgumentCaptor<UserReportPreference> saved =
                ArgumentCaptor.forClass(UserReportPreference.class);
        Mockito.verify(dao).savePreference(saved.capture());
        String json = saved.getValue().getPreferenceValue();

        assertNotNull(json);
        assertTrue("the rest of the preference must still be saved", json.contains("\"en\""));
        assertTrue("the observation must not appear in the persisted preference",
                !json.contains("NE PAS REUTILISER"));
    }

    /**
     * Stripping must not mutate the caller's object: generate() may still be holding the same
     * instance, and blanking a field it is about to render would be a baffling bug.
     */
    @Test
    public void savingPreferencesDoesNotMutateTheCallersRequest() {
        ReportRequest request = new ReportRequest();
        request.setDoctorObservation("Toujours present");

        service.savePreferences(request);

        assertEquals("Toujours present", request.getDoctorObservation());
    }

    @Test
    public void generatingAfterSavingStillRendersTheObservation() {
        ReportRequest request = new ReportRequest();
        request.setDoctorObservation("Doit apparaitre");

        service.savePreferences(request);
        service.generate(patient, request);

        assertEquals("Doit apparaitre", captureDocument().getDoctorObservation());
    }
}
