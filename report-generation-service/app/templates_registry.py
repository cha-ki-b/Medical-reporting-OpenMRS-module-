"""
Template registry - the "settings system to facilitate adding report templates".

A template is a JSON *profile* in `templates/profiles/<id>.json`. Two engines:

  * `builtin`  - the profile only carries a style (colours, fonts, header and
                 footer text, layout switches) and the document is laid out
                 programmatically by `layout_docx.py`. Adding a new corporate
                 look is therefore a ~15-line JSON file with no binary asset,
                 which is what makes template creation genuinely easy.
  * `docxtpl`  - the profile points at an uploaded `.docx` carrying a hospital
                 letterhead and jinja2 placeholders. Full typographic control
                 for the cases where a JSON style is not enough.

Profiles are read from disk on every call so an administrator can drop in a new
one (or POST it through /templates) without restarting the service.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

DEFAULT_STYLE: Dict[str, Any] = {
    "accent": "1F4E79",
    "accent_soft": "DEEAF6",
    "text": "1A1A1A",
    "muted": "5A5A5A",
    "rule": "C9D6E4",
    "zebra": "F5F8FB",
    "font": "Calibri",
    "arabic_font": "Arial",
    "title_size": 20,
    "heading_size": 12,
    "base_size": 10.5,
    "small_size": 8.5,
    "label_column_percent": 34,
    "show_patient_banner": True,
    "show_accent_bar": True,
}


@dataclass
class TemplateProfile:
    id: str
    label: Dict[str, str]
    description: Dict[str, str] = field(default_factory=dict)
    engine: str = "builtin"
    languages: List[str] = field(default_factory=lambda: ["fr", "en", "ar"])
    style: Dict[str, Any] = field(default_factory=dict)
    header_text: Dict[str, str] = field(default_factory=dict)
    footer_text: Dict[str, str] = field(default_factory=dict)
    docx_file: Optional[str] = None
    builtin: bool = False

    def resolved_style(self) -> Dict[str, Any]:
        merged = dict(DEFAULT_STYLE)
        merged.update(self.style or {})
        return merged

    def docx_path(self) -> Optional[Path]:
        if not self.docx_file:
            return None
        # Resolved against the uploads dir and re-checked, so a profile cannot
        # point the renderer at an arbitrary file on disk.
        candidate = (settings.uploads_dir / self.docx_file).resolve()
        if not str(candidate).startswith(str(settings.uploads_dir.resolve())):
            return None
        return candidate if candidate.exists() else None


class TemplateNotFoundError(KeyError):
    pass


# The profiles shipped with the service. Written to disk on first start so an
# administrator can read one as a worked example before authoring their own.
BUILTIN_PROFILES: Dict[str, Dict[str, Any]] = {
    "generic_clinical": {
        "label": {
            "fr": "Rapport clinique standard",
            "en": "Standard clinical report",
            "ar": "تقرير سريري قياسي",
        },
        "description": {
            "fr": "Mise en page neutre, deux colonnes « Donnée : valeur », adaptée à toutes les sections.",
            "en": "Neutral two-column “Data : value” layout, suitable for any selection of sections.",
            "ar": "تخطيط محايد من عمودين «البيان: القيمة» يناسب جميع الأقسام.",
        },
        "engine": "builtin",
        "style": {"accent": "1F4E79", "accent_soft": "DEEAF6"},
    },
    "chu_blida_neuro": {
        "label": {
            "fr": "CHU Blida — Neurochirurgie",
            "en": "CHU Blida — Neurosurgery",
            "ar": "المستشفى الجامعي البليدة — جراحة الأعصاب",
        },
        "description": {
            "fr": "En-tête du service de neurochirurgie du CHU Blida, avec bloc de signature.",
            "en": "CHU Blida neurosurgery department letterhead, with signature block.",
            "ar": "ترويسة قسم جراحة الأعصاب بالمستشفى الجامعي البليدة مع خانة التوقيع.",
        },
        "engine": "builtin",
        "style": {"accent": "1B5E20", "accent_soft": "E3F0E4", "rule": "BBD5BD"},
        "header_text": {
            "fr": "CHU de Blida — Service de Neurochirurgie",
            "en": "CHU Blida — Department of Neurosurgery",
            "ar": "المستشفى الجامعي بالبليدة — قسم جراحة الأعصاب",
        },
        "footer_text": {
            "fr": "CHU de Blida — Service de Neurochirurgie",
            "en": "CHU Blida — Department of Neurosurgery",
            "ar": "المستشفى الجامعي بالبليدة — قسم جراحة الأعصاب",
        },
    },
    "chu_blida_imaging": {
        "label": {
            "fr": "CHU Blida — Compte rendu d'imagerie",
            "en": "CHU Blida — Imaging report",
            "ar": "المستشفى الجامعي البليدة — تقرير التصوير",
        },
        "description": {
            "fr": "Compte rendu d'observation sur imagerie DICOM (cas d'usage 1).",
            "en": "DICOM imaging observation report (use case 1).",
            "ar": "تقرير ملاحظات التصوير الطبي (حالة الاستخدام 1).",
        },
        "engine": "builtin",
        "style": {"accent": "4A148C", "accent_soft": "EDE3F5", "rule": "D3C2E4"},
        "header_text": {
            "fr": "CHU de Blida — Imagerie médicale",
            "en": "CHU Blida — Medical imaging",
            "ar": "المستشفى الجامعي بالبليدة — التصوير الطبي",
        },
    },
    "compact_summary": {
        "label": {
            "fr": "Synthèse compacte",
            "en": "Compact summary",
            "ar": "ملخص مختصر",
        },
        "description": {
            "fr": "Version dense sur peu de pages, utile pour un transfert ou une réunion de staff.",
            "en": "Dense few-page version, useful for a transfer or a staff meeting.",
            "ar": "نسخة مكثفة في صفحات قليلة، مفيدة للتحويل أو اجتماع الفريق.",
        },
        "engine": "builtin",
        "style": {
            "accent": "37474F",
            "accent_soft": "ECEFF1",
            "rule": "CFD8DC",
            "title_size": 16,
            "heading_size": 11,
            "base_size": 9,
            "show_patient_banner": True,
            "show_accent_bar": False,
        },
    },
}


def ensure_builtin_profiles() -> None:
    """Materialise the shipped profiles on disk if they are not there yet."""
    settings.ensure_dirs()
    for profile_id, body in BUILTIN_PROFILES.items():
        path = settings.profiles_dir / f"{profile_id}.json"
        if path.exists():
            continue
        payload = {"id": profile_id, "builtin": True, **body}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_profile_file(path: Path) -> Optional[TemplateProfile]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    profile_id = str(raw.get("id") or path.stem)
    if not ID_PATTERN.match(profile_id):
        return None
    label = raw.get("label")
    if not isinstance(label, dict) or not label:
        label = {"fr": profile_id, "en": profile_id, "ar": profile_id}
    return TemplateProfile(
        id=profile_id,
        label={str(k): str(v) for k, v in label.items()},
        description={str(k): str(v) for k, v in (raw.get("description") or {}).items()},
        engine=str(raw.get("engine") or "builtin"),
        languages=[str(x) for x in (raw.get("languages") or ["fr", "en", "ar"])],
        style=raw.get("style") or {},
        header_text={str(k): str(v) for k, v in (raw.get("header_text") or {}).items()},
        footer_text={str(k): str(v) for k, v in (raw.get("footer_text") or {}).items()},
        docx_file=raw.get("docx_file"),
        builtin=bool(raw.get("builtin", False)),
    )


def list_profiles() -> List[TemplateProfile]:
    ensure_builtin_profiles()
    profiles: List[TemplateProfile] = []
    for path in sorted(settings.profiles_dir.glob("*.json")):
        profile = _load_profile_file(path)
        if profile:
            profiles.append(profile)
    return profiles


def get_profile(template_id: str) -> TemplateProfile:
    for profile in list_profiles():
        if profile.id == template_id:
            return profile
    raise TemplateNotFoundError(template_id)


def save_profile(payload: Dict[str, Any]) -> TemplateProfile:
    ensure_builtin_profiles()
    profile_id = str(payload.get("id") or "").strip().lower()
    if not ID_PATTERN.match(profile_id):
        raise ValueError(
            "Template id must be lowercase alphanumeric with - or _ (max 64 chars)."
        )
    path = settings.profiles_dir / f"{profile_id}.json"
    body = dict(payload)
    body["id"] = profile_id
    body["builtin"] = False
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    profile = _load_profile_file(path)
    if profile is None:
        raise ValueError("Template profile was written but could not be parsed back.")
    return profile


def delete_profile(template_id: str) -> bool:
    """Delete a custom profile. Built-in profiles are protected."""
    profile = get_profile(template_id)
    if profile.builtin or template_id in BUILTIN_PROFILES:
        raise PermissionError(f"'{template_id}' is a built-in template and cannot be deleted.")
    path = settings.profiles_dir / f"{template_id}.json"
    docx = profile.docx_path()
    if docx and docx.exists():
        docx.unlink()
    if path.exists():
        path.unlink()
        return True
    return False
