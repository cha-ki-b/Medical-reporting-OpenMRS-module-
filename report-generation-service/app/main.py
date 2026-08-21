"""
Report Generation Service — HTTP surface.

Serves both medreport use cases through one renderer (ADR-8):

  * use case 1 — per-image observation reports, and
  * use case 2 — full patient reports whose contents the clinician selects.

It knows nothing about OpenMRS, patients-as-entities, privileges or Orthanc.
The OpenMRS `medreport` module decides *what* a user may see and shapes it into
a DocumentContext; this service decides only *how it looks on the page*. That
boundary is what lets the module's authorization model be the single source of
truth (ADR-3).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response

from app import artifacts, renderer, templates_registry
from app.config import settings
from app.schemas import (
    DocumentContext,
    HealthResponse,
    OutputFormat,
    RenderRequest,
    RenderResponse,
    TemplateInfo,
    TemplateListResponse,
)
from app.security import require_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("medreport.rgs")

VERSION = "2.1.0"

_cleanup: Optional[artifacts.CleanupThread] = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _cleanup
    settings.ensure_dirs()
    templates_registry.ensure_builtin_profiles()
    soffice = settings.find_soffice()
    log.info(
        "Report Generation Service %s starting — templates=%s output=%s pdf=%s",
        VERSION,
        settings.templates_dir,
        settings.output_dir,
        soffice or "unavailable (docx/html only)",
    )
    if not settings.auth_token and not settings.allow_anonymous:
        log.warning(
            "MEDREPORT_RGS_TOKEN is not set — every request will be rejected with 503. "
            "Set it, or set MEDREPORT_RGS_ALLOW_ANONYMOUS=true for local development."
        )
    _cleanup = artifacts.CleanupThread()
    _cleanup.start()
    try:
        yield
    finally:
        if _cleanup:
            _cleanup.stop()


app = FastAPI(
    title="Report Generation Service",
    description=(
        "Renders medical reports for the OpenMRS `medreport` module: "
        "DOCX/PDF/HTML/ODT, French/English/Arabic, template profiles."
    ),
    version=VERSION,
    lifespan=lifespan,
)


# ---- health & templates --------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Unauthenticated on purpose: container orchestrators poll it."""
    soffice = settings.find_soffice()
    formats = ["docx", "html"] + (["pdf", "odt"] if soffice else [])
    return HealthResponse(
        status="ok",
        version=VERSION,
        pdf_available=soffice is not None,
        soffice_path=soffice,
        templates=len(templates_registry.list_profiles()),
        formats=formats,
    )


def _template_info(profile: templates_registry.TemplateProfile) -> TemplateInfo:
    return TemplateInfo(
        id=profile.id,
        label=profile.label,
        description=profile.description,
        engine=profile.engine,
        languages=profile.languages,
        builtin=profile.builtin,
        accent=profile.resolved_style().get("accent"),
    )


@app.get(
    "/templates",
    response_model=TemplateListResponse,
    dependencies=[Depends(require_token)],
)
def list_templates() -> TemplateListResponse:
    return TemplateListResponse(
        templates=[_template_info(p) for p in templates_registry.list_profiles()]
    )


@app.post(
    "/templates",
    response_model=TemplateInfo,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
def create_template(payload: Dict[str, Any]) -> TemplateInfo:
    """
    Register a style-profile template. The whole body is the profile JSON:
    `{"id": "...", "label": {...}, "style": {...}, "header_text": {...}}`.
    """
    try:
        profile = templates_registry.save_profile(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _template_info(profile)


@app.post(
    "/templates/upload",
    response_model=TemplateInfo,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_token)],
)
async def upload_template(
    template_id: str = Form(...),
    label_fr: str = Form(...),
    label_en: str = Form(""),
    label_ar: str = Form(""),
    description_fr: str = Form(""),
    file: UploadFile = File(...),
) -> TemplateInfo:
    """Register a hospital-supplied .docx letterhead rendered through docxtpl."""
    template_id = template_id.strip().lower()
    if not templates_registry.ID_PATTERN.match(template_id):
        raise HTTPException(
            status_code=422,
            detail="template_id must be lowercase alphanumeric with - or _ (max 64 chars).",
        )
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="Template file must be a .docx.")

    content = await file.read()
    if len(content) > settings.max_template_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Template exceeds {settings.max_template_upload_bytes} bytes.",
        )
    if not content.startswith(b"PK"):
        # A .docx is a zip; anything else is not one whatever the extension says.
        raise HTTPException(status_code=422, detail="File is not a valid .docx (Office Open XML) document.")

    settings.ensure_dirs()
    stored_name = f"{template_id}.docx"
    (settings.uploads_dir / stored_name).write_bytes(content)

    try:
        profile = templates_registry.save_profile(
            {
                "id": template_id,
                "label": {
                    "fr": label_fr,
                    "en": label_en or label_fr,
                    "ar": label_ar or label_fr,
                },
                "description": {"fr": description_fr} if description_fr else {},
                "engine": "docxtpl",
                "docx_file": stored_name,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _template_info(profile)


@app.delete("/templates/{template_id}", dependencies=[Depends(require_token)])
def delete_template(template_id: str) -> JSONResponse:
    try:
        deleted = templates_registry.delete_profile(template_id)
    except templates_registry.TemplateNotFoundError:
        raise HTTPException(status_code=404, detail=f"No template '{template_id}'.")
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"deleted": deleted, "id": template_id})


# ---- rendering -----------------------------------------------------------


@app.post("/render", response_model=RenderResponse, dependencies=[Depends(require_token)])
def render(request: RenderRequest) -> RenderResponse:
    try:
        profile = templates_registry.get_profile(request.template)
    except templates_registry.TemplateNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown template '{request.template}'. "
                f"Available: {[p.id for p in templates_registry.list_profiles()]}"
            ),
        )

    if request.document is not None:
        context: DocumentContext = request.document
    elif request.data is not None:
        context = renderer.legacy_data_to_context(request.template, request.data)
    else:
        raise HTTPException(
            status_code=422, detail="Either 'document' or 'data' must be supplied."
        )

    warnings: List[str] = []
    requested_format = request.format

    if requested_format in renderer.CONVERTED_FORMATS and not renderer.pdf_available():
        warnings.append(
            f"LibreOffice is unavailable on this host; '{requested_format.value}' was "
            "downgraded to 'docx'. Install LibreOffice or set MEDREPORT_SOFFICE_PATH."
        )
        requested_format = OutputFormat.docx

    try:
        content, extension = renderer.render_document(context, profile, requested_format)
    except renderer.ConversionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except renderer.RenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    stem = artifacts.safe_filename(
        request.filename_hint
        or f"{profile.id}_{context.patient.display_name or 'rapport'}"
    )
    artifact = artifacts.store(content, f"{stem}.{extension}", extension)

    preview_url = None
    preview_format = None
    if request.include_preview:
        if extension in {"pdf", "html"}:
            preview_url = f"/artifacts/{artifact.artifact_id}/preview"
            preview_format = extension
        else:
            try:
                preview_bytes, preview_format = renderer.render_preview(context, profile)
                artifacts.attach(
                    artifact.artifact_id,
                    preview_bytes,
                    f"{stem}.preview.{preview_format}",
                    preview_format,
                )
                preview_url = f"/artifacts/{artifact.artifact_id}/preview"
            except renderer.RenderError as exc:
                warnings.append(f"Preview unavailable: {exc}")

    return RenderResponse(
        artifact_id=artifact.artifact_id,
        filename=artifact.filename,
        format=OutputFormat(extension),
        size_bytes=artifact.size_bytes,
        download_url=f"/artifacts/{artifact.artifact_id}/download",
        preview_url=preview_url,
        preview_format=preview_format,
        pdf_available=renderer.pdf_available(),
        expires_at=artifact.expires_at.isoformat(),
        warnings=warnings,
    )


# ---- artifact retrieval --------------------------------------------------


@app.get("/artifacts/{artifact_id}/download", dependencies=[Depends(require_token)])
def download(artifact_id: str):
    artifact = artifacts.load(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found or expired.")
    return FileResponse(
        path=artifact.path,
        media_type=artifact.media_type,
        filename=artifact.filename,
    )


@app.get("/artifacts/{artifact_id}/preview", dependencies=[Depends(require_token)])
def preview(artifact_id: str):
    """
    Inline rendition for the "preview before download" step.

    Tries the PDF companion first, then HTML, then the artifact itself, so the
    caller gets something viewable regardless of what the host could produce.
    """
    for rendition in ("pdf", "html", None):
        artifact = artifacts.load(artifact_id, rendition=rendition)
        if artifact is not None:
            break
    else:  # pragma: no cover - the None pass always resolves or returns None
        artifact = None

    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found or expired.")

    content = artifact.path.read_bytes()
    return Response(
        content=content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{artifact.filename}"',
            # A preview is PHI rendered into a browser-visible document; keep it
            # out of shared caches and out of any framing site but our own.
            "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        },
    )


@app.delete("/artifacts/{artifact_id}", dependencies=[Depends(require_token)])
def delete_artifact(artifact_id: str) -> JSONResponse:
    """
    Let the caller drop a rendition as soon as it has been persisted on the
    OpenMRS side, rather than waiting out the retention TTL.
    """
    return JSONResponse({"deleted": artifacts.purge(artifact_id), "id": artifact_id})
