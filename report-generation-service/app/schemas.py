"""
Request/response contracts.

Design note - why the context is generic
----------------------------------------
v1 hard-coded one Pydantic model per template (`NeuroReportContext`,
`ImagingReportContext`). That cannot express the second use case, where the
clinician picks *which* sets of data go into the report and a contributing
OpenMRS module (today `patientview`, tomorrow anything else) declares what
those sets even are. A fixed schema would have to be edited here every time a
contributor adds a field, re-coupling this service to OpenMRS internals - the
exact thing ADR-3 keeps apart.

So the contract is now a generic, self-describing document: an ordered tree of
`Section` -> `Field`/`Record` nodes carrying already-localised labels. This
service owns *presentation* (layout, typography, direction, pagination); the
OpenMRS module owns *selection and meaning* (which data, whose privilege,
which language). The two legacy contexts are still accepted so existing SF2/SF3
callers keep working.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Language(str, Enum):
    fr = "fr"
    en = "en"
    ar = "ar"

    @property
    def direction(self) -> str:
        return "rtl" if self is Language.ar else "ltr"


class OutputFormat(str, Enum):
    docx = "docx"
    pdf = "pdf"
    html = "html"
    odt = "odt"


class FieldType(str, Enum):
    text = "text"
    longtext = "longtext"
    number = "number"
    date = "date"
    boolean = "boolean"
    list = "list"


# ---- Document building blocks -------------------------------------------


class DocField(BaseModel):
    """One `Label : value` pair. `label` arrives already translated."""

    model_config = ConfigDict(populate_by_name=True)

    key: str = ""
    label: str
    value: Optional[str] = None
    type: FieldType = FieldType.text
    unit: Optional[str] = None
    emphasis: bool = False

    @field_validator("value", mode="before")
    @classmethod
    def _stringify(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)


class DocRecord(BaseModel):
    """
    One occurrence of a repeating category (a lab draw, a follow-up visit, a
    past surgery). Rendered as a compact sub-block under its section so a
    patient with eight consultations does not become eight identical headings.
    """

    title: Optional[str] = None
    subtitle: Optional[str] = None
    fields: List[DocField] = Field(default_factory=list)


class DocSection(BaseModel):
    """A set of clinical information, e.g. "Démographiques", "Antécédents"."""

    id: str = ""
    title: str
    description: Optional[str] = None
    fields: List[DocField] = Field(default_factory=list)
    records: List[DocRecord] = Field(default_factory=list)
    subsections: List["DocSection"] = Field(default_factory=list)
    note: Optional[str] = None


DocSection.model_rebuild()


class PatientRef(BaseModel):
    family_name: str = ""
    given_name: str = ""
    birthdate: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    identifier: Optional[str] = None

    @property
    def display_name(self) -> str:
        return " ".join(p for p in (self.family_name, self.given_name) if p).strip()


class AuthorRef(BaseModel):
    full_name: str = ""
    role: Optional[str] = None


class ImageObservation(BaseModel):
    """
    A per-image/study observation authored through use case 1, optionally
    embedded into a full patient report ("image id : observation").
    """

    image_label: str = ""
    study_uid: Optional[str] = None
    series_uid: Optional[str] = None
    modality: Optional[str] = None
    study_date: Optional[str] = None
    author: Optional[str] = None
    observed_at: Optional[str] = None
    text: str = ""


class DocumentOptions(BaseModel):
    show_empty_fields: bool = False
    include_table_of_contents: bool = False
    include_signature_block: bool = True
    include_page_numbers: bool = True
    include_generation_footer: bool = True
    confidentiality_notice: bool = True


class DocumentContext(BaseModel):
    """The complete, presentation-ready description of one report."""

    language: Language = Language.fr
    title: Optional[str] = None
    subtitle: Optional[str] = None
    facility: Optional[str] = None
    department: Optional[str] = None
    patient: PatientRef = Field(default_factory=PatientRef)
    author: AuthorRef = Field(default_factory=AuthorRef)
    sections: List[DocSection] = Field(default_factory=list)
    image_observations: List[ImageObservation] = Field(default_factory=list)
    options: DocumentOptions = Field(default_factory=DocumentOptions)

    # Free text the clinician typed in the personalisation window, reproduced verbatim at the
    # very end of the document. Deliberately NOT a Section: sections render before the imaging
    # observations, and this has to come last, after everything the report drew from the
    # record. It is also never translated - it is the author's own words.
    doctor_observation: Optional[str] = None

    generated_at: str = Field(
        default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M")
    )
    reference: Optional[str] = None

    @property
    def direction(self) -> str:
        return self.language.direction


# ---- Legacy v1 contexts (still accepted) ---------------------------------


class LegacyTemplateName(str, Enum):
    chu_blida_neuro = "chu_blida_neuro"
    chu_blida_imaging = "chu_blida_imaging"


# ---- Request / response envelopes ----------------------------------------


class RenderRequest(BaseModel):
    """
    Either `document` (the generic path, used by both use cases now) or `data`
    (the v1 shape) must be supplied. `template` names a registered profile.
    """

    template: str = "generic_clinical"
    format: OutputFormat = OutputFormat.docx
    document: Optional[DocumentContext] = None
    data: Optional[Dict[str, Any]] = None
    include_preview: bool = True
    filename_hint: Optional[str] = None


class RenderedArtifact(BaseModel):
    artifact_id: str
    filename: str
    format: OutputFormat
    size_bytes: int
    download_url: str


class RenderResponse(BaseModel):
    artifact_id: str
    filename: str
    format: OutputFormat
    size_bytes: int
    download_url: str
    preview_url: Optional[str] = None
    preview_format: Optional[str] = None
    pdf_available: bool = True
    expires_at: str
    warnings: List[str] = Field(default_factory=list)


class TemplateInfo(BaseModel):
    id: str
    label: Dict[str, str]
    description: Dict[str, str] = Field(default_factory=dict)
    engine: str
    languages: List[str]
    builtin: bool
    accent: Optional[str] = None


class TemplateListResponse(BaseModel):
    templates: List[TemplateInfo]


class HealthResponse(BaseModel):
    status: str
    version: str
    pdf_available: bool
    soffice_path: Optional[str] = None
    templates: int
    formats: List[str]
