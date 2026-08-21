"""
Render orchestration: DocumentContext -> bytes, in the requested format.

Format matrix (see README "Portability"):

  docx  pure Python (python-docx / docxtpl)   works everywhere
  html  pure Python                           works everywhere
  pdf   LibreOffice headless                  needs LibreOffice
  odt   LibreOffice headless                  needs LibreOffice

When LibreOffice is absent the service does not fail the request: it renders
the .docx, reports `pdf_available: false`, and serves an HTML preview instead,
so previewing before download - a hard requirement - never depends on an
optional native dependency.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from docxtpl import DocxTemplate

from app.config import settings
from app.layout_docx import render_builtin_docx
from app.layout_html import render_html
from app.schemas import (
    AuthorRef,
    DocField,
    DocSection,
    DocumentContext,
    FieldType,
    ImageObservation,
    Language,
    OutputFormat,
    PatientRef,
)
from app.templates_registry import TemplateProfile

log = logging.getLogger(__name__)

NATIVE_FORMATS = {OutputFormat.docx, OutputFormat.html}
CONVERTED_FORMATS = {OutputFormat.pdf, OutputFormat.odt}


class RenderError(RuntimeError):
    pass


class ConversionUnavailableError(RenderError):
    """LibreOffice is not installed, so this format cannot be produced."""


def pdf_available() -> bool:
    return settings.find_soffice() is not None


# ---- LibreOffice conversion ---------------------------------------------


def convert_with_soffice(source: bytes, source_suffix: str, target: str) -> bytes:
    """
    Convert a document via headless LibreOffice.

    Runs in a throwaway directory with a private user profile: concurrent
    conversions otherwise contend on the shared `~/.config/libreoffice` profile
    and intermittently fail with "javaldx" / profile-lock errors under load.
    """
    soffice = settings.find_soffice()
    if not soffice:
        raise ConversionUnavailableError(
            "LibreOffice is not installed or not on PATH; "
            f"cannot convert to {target}. Set MEDREPORT_SOFFICE_PATH to override."
        )

    with tempfile.TemporaryDirectory(prefix="medreport-") as tmp:
        tmp_path = Path(tmp)
        source_path = tmp_path / f"document{source_suffix}"
        source_path.write_bytes(source)
        profile_dir = tmp_path / "profile"
        profile_dir.mkdir()

        command = [
            soffice,
            f"-env:UserInstallation=file:///{profile_dir.as_posix().lstrip('/')}",
            "--headless",
            "--norestore",
            "--invisible",
            "--convert-to",
            target,
            "--outdir",
            str(tmp_path),
            str(source_path),
        ]
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=settings.pdf_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"LibreOffice timed out after {settings.pdf_timeout_seconds}s converting to {target}."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
            raise RenderError(f"LibreOffice failed converting to {target}: {detail}") from exc

        produced = tmp_path / f"document.{target}"
        if not produced.exists():
            detail = (result.stdout or b"").decode("utf-8", "replace").strip()
            raise RenderError(
                f"LibreOffice reported success but produced no .{target} file. {detail}"
            )
        return produced.read_bytes()


# ---- docxtpl path (uploaded hospital letterhead templates) ---------------


def _docxtpl_context(context: DocumentContext) -> Dict[str, Any]:
    """
    Flatten a DocumentContext into the mapping an uploaded template consumes.

    Uploaded templates get both shapes: named top-level keys for the common
    fields (`{{ patient.family_name }}`), and `sections`, so a template can
    also loop `{%p for section in sections %}` over whatever the clinician
    selected without knowing the set in advance.
    """
    payload = context.model_dump(mode="json")
    payload["direction"] = context.direction
    payload["patient_display_name"] = context.patient.display_name
    return payload


def render_docxtpl(context: DocumentContext, template_path: Path) -> bytes:
    document = DocxTemplate(str(template_path))
    document.render(_docxtpl_context(context))
    with tempfile.TemporaryDirectory(prefix="medreport-tpl-") as tmp:
        out = Path(tmp) / "out.docx"
        document.save(str(out))
        return out.read_bytes()


# ---- public entry point --------------------------------------------------


def render_document(
    context: DocumentContext,
    profile: TemplateProfile,
    fmt: OutputFormat,
) -> Tuple[bytes, str]:
    """Render `context` and return `(content, extension)`."""
    if fmt is OutputFormat.html:
        return render_html(context, profile).encode("utf-8"), "html"

    if profile.engine == "docxtpl":
        template_path = profile.docx_path()
        if template_path is None:
            raise RenderError(
                f"Template '{profile.id}' declares engine 'docxtpl' but its .docx file is missing."
            )
        docx_bytes = render_docxtpl(context, template_path)
    else:
        docx_bytes = render_builtin_docx(context, profile)

    if fmt is OutputFormat.docx:
        return docx_bytes, "docx"

    if fmt in CONVERTED_FORMATS:
        return convert_with_soffice(docx_bytes, ".docx", fmt.value), fmt.value

    raise RenderError(f"Unsupported output format: {fmt}")


def render_preview(context: DocumentContext, profile: TemplateProfile) -> Tuple[bytes, str]:
    """
    Produce the best preview this host can manage.

    PDF when LibreOffice is present (matches the printed document exactly),
    HTML otherwise. HTML is always produced as the fallback so the preview
    step never fails.
    """
    if pdf_available():
        try:
            content, _ = render_document(context, profile, OutputFormat.pdf)
            return content, "pdf"
        except RenderError as exc:
            log.warning("PDF preview failed, falling back to HTML: %s", exc)
    return render_html(context, profile).encode("utf-8"), "html"


# ---- v1 backward compatibility -------------------------------------------


def _field(label: str, value: Any, field_type: FieldType = FieldType.text) -> DocField:
    return DocField(label=label, value=value, type=field_type)


def legacy_data_to_context(template_id: str, data: Dict[str, Any]) -> DocumentContext:
    """
    Adapt a v1 `chu_blida_neuro` / `chu_blida_imaging` payload to the generic
    context, so callers written against the old contract keep working while
    everything renders through one code path.
    """
    patient_raw = data.get("patient") or {}
    author_raw = data.get("author") or {}
    patient = PatientRef(
        family_name=patient_raw.get("family_name", ""),
        given_name=patient_raw.get("given_name", ""),
        birthdate=patient_raw.get("birthdate"),
        gender=patient_raw.get("gender"),
        identifier=patient_raw.get("identifier"),
    )
    author = AuthorRef(full_name=author_raw.get("full_name", ""))
    context = DocumentContext(patient=patient, author=author)
    if data.get("generated_at"):
        context.generated_at = str(data["generated_at"])

    if template_id == "chu_blida_imaging":
        study = data.get("study") or {}
        observation = data.get("observation") or {}
        context.image_observations = [
            ImageObservation(
                image_label=study.get("uid", ""),
                study_uid=study.get("uid"),
                modality=study.get("modality"),
                study_date=study.get("date"),
                author=author.full_name,
                text=observation.get("text", ""),
            )
        ]
        return context

    summary = data.get("summary") or {}
    antecedents = data.get("antecedents") or {}
    exam = data.get("exam") or {}
    sections = [
        DocSection(
            id="summary",
            title="Résumé",
            fields=[
                _field("Synthèse", summary.get("text"), FieldType.longtext),
                _field("Glasgow", summary.get("gcs")),
                _field("Karnofsky", summary.get("karnofsky")),
            ],
        ),
        DocSection(
            id="antecedents",
            title="Antécédents",
            fields=[
                _field("Motif d'hospitalisation", antecedents.get("admission_reason"), FieldType.longtext),
                _field("Antécédents médicaux", antecedents.get("medical_history"), FieldType.longtext),
                _field("Antécédents chirurgicaux", antecedents.get("surgical_history"), FieldType.longtext),
            ],
        ),
        DocSection(
            id="exam",
            title="Examen clinique",
            fields=[
                _field("Examen général", exam.get("general"), FieldType.longtext),
                _field("Examen neurologique", exam.get("neurological"), FieldType.longtext),
            ],
        ),
        DocSection(
            id="diagnosis",
            title="Diagnostic",
            fields=[_field("Diagnostic", (data.get("diagnosis") or {}).get("text"), FieldType.longtext)],
        ),
        DocSection(
            id="pathology",
            title="Anatomopathologie",
            fields=[_field("Anatomopathologie", (data.get("pathology") or {}).get("text"), FieldType.longtext)],
        ),
    ]
    context.sections = sections
    context.language = Language.fr
    return context
