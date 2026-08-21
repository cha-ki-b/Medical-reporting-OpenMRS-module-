"""
Render one representative report in every supported language and format.

Used to eyeball the output and to prove the whole pipeline end to end without an OpenMRS
instance: it builds the same DocumentContext the medreport module posts, and writes the
results to `samples/`. Formats needing LibreOffice are skipped with a note when it is absent,
so this runs on any developer machine.

    python scripts/make_samples.py [output-dir]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import renderer, templates_registry  # noqa: E402
from app.schemas import DocumentContext, OutputFormat  # noqa: E402

SAMPLE = {
    "title": "Rapport médical complet",
    "subtitle": "Service de Neurochirurgie — synthèse pré-opératoire",
    "patient": {
        "family_name": "BENALI",
        "given_name": "Yacine",
        "birthdate": "12/04/1978",
        "age": "48",
        "gender": "M",
        "identifier": "CHU-2026-00412",
    },
    "author": {"full_name": "Dr. Amina Kaci", "role": "Neurochirurgien"},
    "reference": "RPT-2026-0142",
    "sections": [
        {
            "id": "core.demographics",
            "title": "Données démographiques",
            "description": "Identité et coordonnées du patient, issues du dossier OpenMRS.",
            "fields": [
                {"key": "profession", "label": "Profession", "value": "Enseignant"},
                {"key": "city", "label": "Commune / Ville", "value": "Blida"},
                {"key": "phone", "label": "Téléphone", "value": "0555 12 34 56"},
            ],
        },
        {
            "id": "patientview.admission",
            "title": "Motif d'hospitalisation",
            "records": [
                {
                    "title": "02/08/2026",
                    "fields": [
                        {"key": "admissionReason", "label": "Motif d'admission",
                         "value": "Céphalées progressives avec troubles visuels.", "type": "longtext"},
                        {"key": "diagnosisDelayDays", "label": "Délai diagnostique",
                         "value": "94", "unit": "j"},
                        {"key": "responsibleNeurosurgeon", "label": "Neurochirurgien responsable",
                         "value": "Dr. Amina Kaci"},
                    ],
                }
            ],
        },
        {
            "id": "patientview.medicalHistory",
            "title": "Antécédents médicaux",
            "fields": [
                {"key": "hypertension", "label": "Hypertension artérielle", "value": "true", "type": "boolean"},
                {"key": "diabetes", "label": "Diabète", "value": "false", "type": "boolean"},
                {"key": "allergies", "label": "Allergies", "value": "Pénicilline", "emphasis": True},
                {"key": "chronicTreatment", "label": "Traitement chronique",
                 "value": "Amlodipine 5 mg/j\nAtorvastatine 20 mg/j", "type": "longtext"},
            ],
        },
        {
            "id": "patientview.diagnosis",
            "title": "Diagnostic neurochirurgical",
            "description": "Diagnostic, siège lésionnel, latéralité et taille (Fiche §8).",
            "fields": [
                {"key": "diagnosis", "label": "Diagnostic", "value": "Méningiome frontal", "emphasis": True},
                {"key": "lesionLocation", "label": "Siège de la lésion", "value": "Convexité frontale"},
                {"key": "laterality", "label": "Latéralité", "value": "Gauche"},
                {"key": "size", "label": "Taille", "value": "32", "unit": "mm"},
                {"key": "lesionCount", "label": "Nombre de lésions", "value": "1"},
            ],
            "subsections": [
                {
                    "id": "patientview.pathology",
                    "title": "Anatomopathologie",
                    "fields": [
                        {"key": "finalDiagnosis", "label": "Diagnostic final",
                         "value": "Méningiome méningothélial", "emphasis": True},
                        {"key": "whoGrade", "label": "Grade OMS", "value": "Grade I"},
                    ],
                }
            ],
        },
        {
            "id": "patientview.vitals",
            "title": "Constantes",
            "records": [
                {
                    "title": "10/08/2026",
                    "subtitle": "Consultation pré-opératoire",
                    "fields": [
                        {"key": "bp", "label": "Tension artérielle", "value": "13/8"},
                        {"key": "hr", "label": "Fréquence cardiaque", "value": "72", "unit": "bpm"},
                        {"key": "spo2", "label": "SpO2", "value": "98", "unit": "%"},
                    ],
                },
                {
                    "title": "14/08/2026",
                    "fields": [
                        {"key": "bp", "label": "Tension artérielle", "value": "12/7"},
                        {"key": "hr", "label": "Fréquence cardiaque", "value": "68", "unit": "bpm"},
                    ],
                },
            ],
        },
    ],
    "image_observations": [
        {
            "image_label": "IRM cérébrale — 14/08/2026",
            "study_uid": "1.2.840.113619.2.55.3.1234",
            "modality": "MR",
            "study_date": "14/08/2026",
            "author": "Dr. Amina Kaci",
            "observed_at": "14/08/2026 09:20",
            "text": (
                "Lésion extra-axiale frontale gauche, de 32 mm de grand axe, "
                "à base d'implantation durale large.\n"
                "Prise de contraste homogène et intense. Pas d'engagement."
            ),
        },
        {
            "image_label": "TDM cérébrale — 02/08/2026",
            "study_uid": "1.2.840.113619.2.55.3.9876",
            "modality": "CT",
            "study_date": "02/08/2026",
            "author": "Dr. Karim Belkacem",
            "observed_at": "02/08/2026 16:45",
            "text": "Processus expansif frontal gauche avec oedème périlésionnel modéré.",
        },
    ],
    "options": {
        "include_table_of_contents": True,
        "show_empty_fields": False,
        "include_signature_block": True,
        "confidentiality_notice": True,
    },
}

ARABIC_OVERRIDES = {
    "title": "التقرير الطبي الكامل",
    "subtitle": "قسم جراحة الأعصاب — ملخص ما قبل الجراحة",
    "sections": [
        {
            "id": "demographics",
            "title": "البيانات الديموغرافية",
            "fields": [
                {"key": "profession", "label": "المهنة", "value": "أستاذ"},
                {"key": "city", "label": "البلدية", "value": "البليدة"},
            ],
        },
        {
            "id": "diagnosis",
            "title": "التشخيص الجراحي العصبي",
            "fields": [
                {"key": "diagnosis", "label": "التشخيص", "value": "ورم سحائي جبهي", "emphasis": True},
                {"key": "laterality", "label": "الجانب", "value": "أيسر"},
                {"key": "size", "label": "الحجم", "value": "32", "unit": "مم"},
                {"key": "recurrence", "label": "انتكاس", "value": "false", "type": "boolean"},
            ],
        },
    ],
    "image_observations": [
        {
            "image_label": "التصوير بالرنين المغناطيسي — 14/08/2026",
            "study_uid": "1.2.840.113619.2.55.3.1234",
            "modality": "MR",
            "author": "د. أمينة قاسي",
            "text": "آفة خارج المحور في الفص الجبهي الأيسر بقطر 32 مم.",
        }
    ],
}


def build(language: str) -> DocumentContext:
    payload = dict(SAMPLE)
    payload["language"] = language
    if language == "ar":
        payload = {**payload, **ARABIC_OVERRIDES}
    elif language == "en":
        payload["title"] = "Complete medical report"
        payload["subtitle"] = "Department of Neurosurgery — pre-operative summary"
    return DocumentContext.model_validate(payload)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "samples"
    out.mkdir(parents=True, exist_ok=True)
    templates_registry.ensure_builtin_profiles()

    have_soffice = renderer.pdf_available()
    print(f"LibreOffice: {'available' if have_soffice else 'NOT available - skipping pdf/odt'}")

    combinations = [
        ("fr", "chu_blida_neuro", [OutputFormat.docx, OutputFormat.html, OutputFormat.pdf]),
        ("en", "generic_clinical", [OutputFormat.docx, OutputFormat.html]),
        ("ar", "chu_blida_neuro", [OutputFormat.docx, OutputFormat.html, OutputFormat.pdf]),
        ("fr", "compact_summary", [OutputFormat.html]),
    ]

    written = 0
    for language, template_id, formats in combinations:
        profile = templates_registry.get_profile(template_id)
        context = build(language)
        for fmt in formats:
            if fmt in renderer.CONVERTED_FORMATS and not have_soffice:
                continue
            content, extension = renderer.render_document(context, profile, fmt)
            path = out / f"rapport_{template_id}_{language}.{extension}"
            path.write_bytes(content)
            written += 1
            print(f"  {path.name:45s} {len(content):>9,} bytes")

    print(f"\n{written} sample(s) written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
