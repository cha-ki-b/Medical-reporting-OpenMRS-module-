"""
Short-lived storage for generated documents.

v1 returned a filesystem path and exposed `GET /download?path=...`, which let
any caller read any file the process could reach. Here a render produces an
opaque `artifact_id` instead, and download/preview resolve that id against a
manifest - a client-supplied path never reaches the filesystem.

Artifacts hold PHI, so they are not kept: a background sweep removes anything
past its TTL. The authoritative copy of a report lives in OpenMRS as a Complex
Obs; what is stored here is a transient render.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MANIFEST = "artifact.json"


@dataclass
class Artifact:
    artifact_id: str
    filename: str
    format: str
    size_bytes: int
    created_at: datetime
    expires_at: datetime
    path: Path

    @property
    def media_type(self) -> str:
        return {
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
            "html": "text/html; charset=utf-8",
            "odt": "application/vnd.oasis.opendocument.text",
        }.get(self.format, "application/octet-stream")


def safe_filename(raw: str, fallback: str = "rapport") -> str:
    """
    Reduce an arbitrary hint to a filename that is safe on all three OSes.

    Accents are folded rather than dropped so `Rapport_Médical` stays readable,
    and every path separator and reserved character is removed - the result is
    only ever used as a leaf name inside a directory we created.
    """
    normalised = unicodedata.normalize("NFKD", raw or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_only).strip("._-")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    return (cleaned or fallback)[:80]


def _artifact_dir(artifact_id: str) -> Path:
    return settings.output_dir / artifact_id


def store(content: bytes, filename: str, fmt: str) -> Artifact:
    settings.ensure_dirs()
    artifact_id = uuid.uuid4().hex
    directory = _artifact_dir(artifact_id)
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / filename
    path.write_bytes(content)

    now = datetime.now(timezone.utc)
    artifact = Artifact(
        artifact_id=artifact_id,
        filename=filename,
        format=fmt,
        size_bytes=len(content),
        created_at=now,
        expires_at=now + timedelta(minutes=settings.artifact_ttl_minutes),
        path=path,
    )
    (directory / _MANIFEST).write_text(
        json.dumps(
            {
                "artifact_id": artifact.artifact_id,
                "filename": artifact.filename,
                "format": artifact.format,
                "size_bytes": artifact.size_bytes,
                "created_at": artifact.created_at.isoformat(),
                "expires_at": artifact.expires_at.isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return artifact


def attach(artifact_id: str, content: bytes, filename: str, fmt: str) -> Path:
    """Add a companion rendition (e.g. the PDF preview of a .docx) to an artifact."""
    directory = _artifact_dir(artifact_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(content)
    manifest_path = directory / _MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest.setdefault("renditions", {})[fmt] = filename
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def load(artifact_id: str, rendition: Optional[str] = None) -> Optional[Artifact]:
    """
    Resolve an artifact id to a file on disk.

    The id is validated against a strict 32-hex-char pattern before it is used
    in a path, and the resolved path is re-checked to be inside the output
    directory, so `..` or an absolute path can never escape.
    """
    if not artifact_id or not _ID_RE.match(artifact_id):
        return None
    directory = _artifact_dir(artifact_id).resolve()
    if not str(directory).startswith(str(settings.output_dir.resolve())):
        return None
    manifest_path = directory / _MANIFEST
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fmt = manifest.get("format", "docx")
    filename = manifest.get("filename", "")
    if rendition and rendition != fmt:
        renditions = manifest.get("renditions") or {}
        if rendition not in renditions:
            return None
        filename = renditions[rendition]
        fmt = rendition

    path = (directory / filename).resolve()
    if not str(path).startswith(str(directory)) or not path.exists():
        return None

    expires_at = datetime.fromisoformat(manifest["expires_at"])
    if expires_at <= datetime.now(timezone.utc):
        purge(artifact_id)
        return None

    return Artifact(
        artifact_id=artifact_id,
        filename=filename,
        format=fmt,
        size_bytes=path.stat().st_size,
        created_at=datetime.fromisoformat(manifest["created_at"]),
        expires_at=expires_at,
        path=path,
    )


def purge(artifact_id: str) -> bool:
    if not _ID_RE.match(artifact_id or ""):
        return False
    directory = _artifact_dir(artifact_id)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
        return True
    return False


def sweep_expired() -> int:
    """Delete every artifact whose TTL has elapsed. Returns how many were removed."""
    if not settings.output_dir.exists():
        return 0
    removed = 0
    now = datetime.now(timezone.utc)
    for directory in settings.output_dir.iterdir():
        if not directory.is_dir():
            continue
        manifest_path = directory / _MANIFEST
        try:
            expires_at = datetime.fromisoformat(
                json.loads(manifest_path.read_text(encoding="utf-8"))["expires_at"]
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            # An unreadable manifest means we cannot know the retention
            # deadline; fall back to directory mtime so PHI still expires.
            try:
                age = now.timestamp() - directory.stat().st_mtime
            except OSError:
                continue
            if age > settings.artifact_ttl_minutes * 60:
                shutil.rmtree(directory, ignore_errors=True)
                removed += 1
            continue
        if expires_at <= now:
            shutil.rmtree(directory, ignore_errors=True)
            removed += 1
    return removed


class CleanupThread(threading.Thread):
    """Periodic retention sweep, started with the app and stopped with it."""

    def __init__(self) -> None:
        super().__init__(name="artifact-cleanup", daemon=True)
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                removed = sweep_expired()
                if removed:
                    log.info("Retention sweep removed %d expired artifact(s).", removed)
            except Exception:  # never let the sweeper kill itself
                log.exception("Retention sweep failed.")
            self._stop.wait(settings.cleanup_interval_seconds)

    def stop(self) -> None:
        self._stop.set()
