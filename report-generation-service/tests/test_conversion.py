"""
Tests for the LibreOffice conversion path.

LibreOffice is not pip-installable and is absent from most developer machines, so the
PDF/ODT path would otherwise stay completely untested until it reached the deployment box.

These tests substitute `subprocess.run` with a fake that honours LibreOffice's actual CLI
contract - read `--convert-to <fmt>` and `--outdir <dir>`, write `<stem>.<fmt>` there - and
assert on everything this service is responsible for: how the command line is built, the
private user profile, how the produced file is located, and the behaviour on failure,
timeout, and silent non-production.

An earlier version of this file spawned a real stub executable instead. That turned out to
test the environment rather than the code: this project's path contains a non-ASCII
character, and `cmd.exe` reads `.bat` files in the OEM codepage, so the stub failed to
resolve its own interpreter on Windows while passing on Linux. Faking at the `subprocess.run`
boundary keeps the tests about our logic and identical on every platform.

What remains unverified here is LibreOffice's own rendering fidelity, which is validated by
running the Docker image (README §3) - the deployment pins the version anyway.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


class FakeSoffice:
    """Stands in for the LibreOffice binary at the subprocess boundary."""

    def __init__(self, *, behaviour: str = "convert"):
        self.behaviour = behaviour
        self.command: list[str] = []

    def __call__(self, command, **kwargs):
        self.command = list(command)

        if self.behaviour == "timeout":
            raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 1))
        if self.behaviour == "fail":
            raise subprocess.CalledProcessError(
                returncode=1, cmd=command,
                stderr=b"Error: source file could not be loaded",
            )
        if self.behaviour == "silent":
            # Exit 0 having produced nothing - LibreOffice really does this on some inputs.
            return subprocess.CompletedProcess(command, 0, b"", b"")

        fmt = command[command.index("--convert-to") + 1]
        outdir = Path(command[command.index("--outdir") + 1])
        source = Path(command[-1])
        (outdir / f"{source.stem}.{fmt}").write_bytes(b"%PDF-1.4 stub output")
        return subprocess.CompletedProcess(command, 0, b"", b"")


@pytest.fixture()
def soffice(app_env, monkeypatch):
    """Point the service at a discoverable binary and fake the process spawn."""
    from app import renderer
    from app.config import settings

    monkeypatch.setattr(settings, "find_soffice", lambda: "/usr/bin/soffice")

    def install(behaviour: str = "convert") -> FakeSoffice:
        fake = FakeSoffice(behaviour=behaviour)
        monkeypatch.setattr(renderer.subprocess, "run", fake)
        return fake

    return install


# ---- the command we build ------------------------------------------------


def test_conversion_returns_the_produced_file(soffice):
    from app import renderer

    soffice()
    assert renderer.convert_with_soffice(b"docx", ".docx", "pdf") == b"%PDF-1.4 stub output"


def test_the_command_requests_the_right_format_in_headless_mode(soffice):
    from app import renderer

    fake = soffice()
    renderer.convert_with_soffice(b"docx", ".docx", "pdf")

    assert "--headless" in fake.command
    assert fake.command[fake.command.index("--convert-to") + 1] == "pdf"
    assert "--outdir" in fake.command
    # No restore prompt, no splash: this runs unattended in a container.
    assert "--norestore" in fake.command


def test_odt_is_requested_the_same_way(soffice):
    from app import renderer

    fake = soffice()
    renderer.convert_with_soffice(b"docx", ".docx", "odt")
    assert fake.command[fake.command.index("--convert-to") + 1] == "odt"


def test_each_conversion_gets_a_private_libreoffice_profile(soffice):
    """
    Concurrent conversions otherwise contend on the shared ~/.config/libreoffice profile and
    fail intermittently under load - the exact failure this flag prevents.
    """
    from app import renderer

    fake = soffice()
    renderer.convert_with_soffice(b"docx", ".docx", "pdf")

    profile_args = [a for a in fake.command if a.startswith("-env:UserInstallation=")]
    assert len(profile_args) == 1
    assert profile_args[0].startswith("-env:UserInstallation=file:///")


def test_two_conversions_do_not_share_a_profile_or_workspace(soffice):
    from app import renderer

    fake = soffice()
    renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    first = [a for a in fake.command if a.startswith("-env:")][0]

    renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    second = [a for a in fake.command if a.startswith("-env:")][0]

    assert first != second


def test_the_working_directory_is_removed_afterwards(soffice):
    """A conversion writes PHI to a temp directory; it must not outlive the call."""
    from app import renderer

    fake = soffice()
    renderer.convert_with_soffice(b"docx", ".docx", "pdf")

    outdir = Path(fake.command[fake.command.index("--outdir") + 1])
    assert not outdir.exists()


# ---- failure handling ----------------------------------------------------


def test_a_failing_conversion_surfaces_libreoffices_own_message(soffice):
    from app import renderer

    soffice("fail")
    with pytest.raises(renderer.RenderError) as failure:
        renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    assert "could not be loaded" in str(failure.value)


def test_a_silent_non_production_is_not_mistaken_for_success(soffice):
    from app import renderer

    soffice("silent")
    with pytest.raises(renderer.RenderError) as failure:
        renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    assert "produced no" in str(failure.value)


def test_a_hanging_conversion_is_killed_by_the_timeout(soffice):
    from app import renderer

    soffice("timeout")
    with pytest.raises(renderer.RenderError) as failure:
        renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    assert "timed out" in str(failure.value)


def test_a_missing_binary_raises_an_actionable_error(app_env, monkeypatch):
    from app import renderer
    from app.config import settings

    monkeypatch.setattr(settings, "find_soffice", lambda: None)
    with pytest.raises(renderer.ConversionUnavailableError) as failure:
        renderer.convert_with_soffice(b"docx", ".docx", "pdf")
    assert "MEDREPORT_SOFFICE_PATH" in str(failure.value)


def test_pdf_availability_tracks_binary_discovery(app_env, monkeypatch):
    from app import renderer
    from app.config import settings

    monkeypatch.setattr(settings, "find_soffice", lambda: "/usr/bin/soffice")
    assert renderer.pdf_available() is True

    monkeypatch.setattr(settings, "find_soffice", lambda: None)
    assert renderer.pdf_available() is False


# ---- end to end through the renderer -------------------------------------


def test_render_document_produces_pdf_end_to_end(soffice, document):
    """The whole path: DocumentContext -> real .docx -> LibreOffice -> pdf bytes."""
    from app import renderer, templates_registry
    from app.schemas import DocumentContext, OutputFormat

    fake = soffice()
    profile = templates_registry.get_profile("chu_blida_neuro")
    content, extension = renderer.render_document(
        DocumentContext.model_validate(document), profile, OutputFormat.pdf
    )

    assert extension == "pdf"
    assert content == b"%PDF-1.4 stub output"
    # What we hand LibreOffice must be a genuine Office Open XML package, not a placeholder.
    source = Path(fake.command[-1])
    assert source.name == "document.docx"


def test_preview_prefers_pdf_when_libreoffice_is_present(soffice, document):
    from app import renderer, templates_registry
    from app.schemas import DocumentContext

    soffice()
    profile = templates_registry.get_profile("generic_clinical")
    content, kind = renderer.render_preview(DocumentContext.model_validate(document), profile)

    assert kind == "pdf"
    assert content.startswith(b"%PDF")


def test_preview_falls_back_to_html_when_conversion_fails(soffice, document):
    """A broken LibreOffice must degrade the preview, never remove it."""
    from app import renderer, templates_registry
    from app.schemas import DocumentContext

    soffice("fail")
    profile = templates_registry.get_profile("generic_clinical")
    content, kind = renderer.render_preview(DocumentContext.model_validate(document), profile)

    assert kind == "html"
    assert b"<!doctype html>" in content.lower()


def test_the_api_reports_pdf_as_available_when_it_is(client, document, monkeypatch):
    """/health and /render must agree with what the host can actually do."""
    from app import renderer
    from app.config import settings

    monkeypatch.setattr(settings, "find_soffice", lambda: "/usr/bin/soffice")
    monkeypatch.setattr(renderer.subprocess, "run", FakeSoffice())

    health = client.get("/health").json()
    assert health["pdf_available"] is True
    assert "pdf" in health["formats"] and "odt" in health["formats"]

    body = client.post(
        "/render", json={"template": "chu_blida_neuro", "format": "pdf", "document": document}
    ).json()
    assert body["format"] == "pdf"
    assert body["warnings"] == []
    assert client.get(body["download_url"]).content.startswith(b"%PDF")
