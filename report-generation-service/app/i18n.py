"""
Static document chrome (page furniture) in the three supported languages.

Deliberately small: every *clinical* label is translated on the OpenMRS side
and arrives pre-localised in the DocumentContext, because that is where the
concept dictionary and the module message bundles live. Duplicating clinical
vocabulary here would create two sources of truth for the same wording.
What remains here is the handful of strings this service itself emits.
"""

from __future__ import annotations

from typing import Dict

STRINGS: Dict[str, Dict[str, str]] = {
    "fr": {
        "doctor_observation": "Observations du médecin",
        "report_title": "Rapport médical",
        "patient": "Patient",
        "identifier": "Identifiant",
        "birthdate": "Date de naissance",
        "age": "Âge",
        "gender": "Sexe",
        "author": "Rédigé par",
        "generated_at": "Généré le",
        "reference": "Référence",
        "table_of_contents": "Sommaire",
        "image_observations": "Observations sur imagerie",
        "study": "Étude",
        "series": "Série",
        "modality": "Modalité",
        "study_date": "Date de l'examen",
        "observed_at": "Observation du",
        "signature": "Signature et cachet",
        "page": "Page",
        "of": "sur",
        "confidential": "Document médical confidentiel — usage strictement réservé au personnel autorisé.",
        "generated_footer": "Document généré automatiquement par OpenMRS / medreport.",
        "not_recorded": "Non renseigné",
        "yes": "Oui",
        "no": "Non",
        "no_data": "Aucune donnée disponible pour les sections sélectionnées.",
    },
    "en": {
        "doctor_observation": "Doctor observations",
        "report_title": "Medical report",
        "patient": "Patient",
        "identifier": "Identifier",
        "birthdate": "Date of birth",
        "age": "Age",
        "gender": "Sex",
        "author": "Authored by",
        "generated_at": "Generated on",
        "reference": "Reference",
        "table_of_contents": "Contents",
        "image_observations": "Imaging observations",
        "study": "Study",
        "series": "Series",
        "modality": "Modality",
        "study_date": "Study date",
        "observed_at": "Observed on",
        "signature": "Signature and stamp",
        "page": "Page",
        "of": "of",
        "confidential": "Confidential medical document — restricted to authorised personnel.",
        "generated_footer": "Document generated automatically by OpenMRS / medreport.",
        "not_recorded": "Not recorded",
        "yes": "Yes",
        "no": "No",
        "no_data": "No data available for the selected sections.",
    },
    "ar": {
        "doctor_observation": "ملاحظات الطبيب",
        "report_title": "التقرير الطبي",
        "patient": "المريض",
        "identifier": "المعرّف",
        "birthdate": "تاريخ الميلاد",
        "age": "العمر",
        "gender": "الجنس",
        "author": "حرّره",
        "generated_at": "تاريخ الإصدار",
        "reference": "المرجع",
        "table_of_contents": "المحتويات",
        "image_observations": "ملاحظات التصوير",
        "study": "الدراسة",
        "series": "السلسلة",
        "modality": "نوع التصوير",
        "study_date": "تاريخ الفحص",
        "observed_at": "تاريخ الملاحظة",
        "signature": "التوقيع والختم",
        "page": "صفحة",
        "of": "من",
        "confidential": "وثيقة طبية سرية — مخصصة للموظفين المصرح لهم فقط.",
        "generated_footer": "وثيقة أُنشئت آليًا بواسطة OpenMRS / medreport.",
        "not_recorded": "غير مسجل",
        "yes": "نعم",
        "no": "لا",
        "no_data": "لا توجد بيانات متاحة للأقسام المحددة.",
    },
}


def t(language: str, key: str) -> str:
    """Look up `key`, falling back to French then to the key itself."""
    lang = language if language in STRINGS else "fr"
    return STRINGS[lang].get(key) or STRINGS["fr"].get(key) or key
