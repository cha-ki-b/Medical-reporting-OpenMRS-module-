"""
Runtime configuration for the Report Generation Service.

Everything is environment-driven so the same image/checkout runs unchanged on
Linux (Docker, the CHU Blida deployment target), Windows and macOS (developer
machines) - see README "Portability". No value here is a secret by default;
the shared token must be supplied by the operator.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser().resolve() if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Resolved once at import time; read as `from app.config import settings`."""

    def __init__(self) -> None:
        self.base_dir: Path = _BASE_DIR
        self.templates_dir: Path = _env_path("MEDREPORT_TEMPLATES_DIR", _BASE_DIR / "templates")
        self.profiles_dir: Path = self.templates_dir / "profiles"
        self.uploads_dir: Path = self.templates_dir / "uploads"
        self.output_dir: Path = _env_path("MEDREPORT_OUTPUT_DIR", _BASE_DIR / "output")

        # Shared-secret auth between the OpenMRS `medreport` module and this
        # service. Both run inside the same private docker network in the
        # target deployment, but the token means a compromised neighbour
        # container still cannot render/read PHI documents.
        self.auth_token: str = os.getenv("MEDREPORT_RGS_TOKEN", "").strip()
        self.allow_anonymous: bool = _env_bool("MEDREPORT_RGS_ALLOW_ANONYMOUS", False)

        # Generated documents hold PHI. They are deleted once this many minutes
        # have elapsed, whether or not the caller downloaded them (the OpenMRS
        # side persists the authoritative copy as a Complex Obs).
        self.artifact_ttl_minutes: int = _env_int("MEDREPORT_ARTIFACT_TTL_MINUTES", 30)
        self.cleanup_interval_seconds: int = _env_int("MEDREPORT_CLEANUP_INTERVAL_SECONDS", 300)

        self.pdf_timeout_seconds: int = _env_int("MEDREPORT_PDF_TIMEOUT_SECONDS", 60)
        self.max_template_upload_bytes: int = _env_int(
            "MEDREPORT_MAX_TEMPLATE_UPLOAD_BYTES", 10 * 1024 * 1024
        )

        self._soffice_override: str = os.getenv("MEDREPORT_SOFFICE_PATH", "").strip()

    # -- LibreOffice discovery ------------------------------------------------

    def find_soffice(self) -> str | None:
        """
        Locate a headless LibreOffice binary across the three supported OSes.

        Returns None when LibreOffice is not installed. That is a supported
        configuration, not an error: .docx and .html rendering are pure Python
        and keep working; only PDF/ODT conversion becomes unavailable and the
        API reports `pdf_available: false` instead of failing the request.
        """
        if self._soffice_override:
            return self._soffice_override if Path(self._soffice_override).exists() else None

        for name in ("soffice", "libreoffice", "soffice.exe"):
            found = shutil.which(name)
            if found:
                return found

        candidates: list[Path] = []
        if sys.platform == "darwin":
            candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
        elif sys.platform.startswith("win"):
            for root in (r"C:\Program Files\LibreOffice", r"C:\Program Files (x86)\LibreOffice"):
                candidates.append(Path(root) / "program" / "soffice.exe")
        else:
            candidates += [
                Path("/usr/bin/soffice"),
                Path("/usr/lib/libreoffice/program/soffice"),
                Path("/snap/bin/libreoffice"),
                Path("/opt/libreoffice/program/soffice"),
            ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def ensure_dirs(self) -> None:
        for directory in (self.templates_dir, self.profiles_dir, self.uploads_dir, self.output_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
