"""End-to-end checks over the HTTP surface."""

from __future__ import annotations

import io
import zipfile

import pytest


def _docx_text(content: bytes) -> str:
    """Extract the visible text of a .docx without needing python-docx here."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


# ---- health & auth -------------------------------------------------------


def test_health_is_public_and_reports_capabilities(client):
    client.headers.pop("X-Medreport-Token", None)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "docx" in body["formats"]
    assert "html" in body["formats"]
    assert body["templates"] >= 4


def test_render_requires_the_shared_token(client, document):
    client.headers.pop("X-Medreport-Token", None)
    response = client.post("/render", json={"template": "generic_clinical", "document": document})
    assert response.status_code == 401


def test_wrong_token_is_rejected(client, document):
    client.headers["X-Medreport-Token"] = "not-the-token"
    response = client.post("/render", json={"template": "generic_clinical", "document": document})
    assert response.status_code == 401


def test_bearer_authorization_header_is_accepted(client, document):
    from tests.conftest import TEST_TOKEN

    client.headers.pop("X-Medreport-Token", None)
    client.headers["Authorization"] = f"Bearer {TEST_TOKEN}"
    response = client.post("/render", json={"template": "generic_clinical", "document": document})
    assert response.status_code == 200


# ---- templates -----------------------------------------------------------


def test_builtin_templates_are_listed_with_localised_labels(client):
    response = client.get("/templates")
    assert response.status_code == 200
    templates = {t["id"]: t for t in response.json()["templates"]}
    assert {"generic_clinical", "chu_blida_neuro", "chu_blida_imaging", "compact_summary"} <= set(templates)
    assert set(templates["chu_blida_neuro"]["label"]) >= {"fr", "en", "ar"}
    assert templates["chu_blida_neuro"]["builtin"] is True


def test_a_new_template_can_be_registered_and_used(client, document):
    created = client.post(
        "/templates",
        json={
            "id": "clinique_es_salem",
            "label": {"fr": "Clinique Es-Salem", "en": "Es-Salem Clinic", "ar": "عيادة السلام"},
            "engine": "builtin",
            "style": {"accent": "B71C1C", "accent_soft": "FBE9E7"},
            "header_text": {"fr": "Clinique Es-Salem — Alger"},
        },
    )
    assert created.status_code == 201
    assert created.json()["accent"] == "B71C1C"

    rendered = client.post(
        "/render",
        json={"template": "clinique_es_salem", "format": "html", "document": document},
    )
    assert rendered.status_code == 200
    preview = client.get(rendered.json()["preview_url"])
    assert "Clinique Es-Salem — Alger" in preview.text
    assert "#B71C1C" in preview.text


def test_builtin_templates_cannot_be_deleted(client):
    response = client.delete("/templates/chu_blida_neuro")
    assert response.status_code == 409


def test_unknown_template_is_a_404(client, document):
    response = client.post("/render", json={"template": "does_not_exist", "document": document})
    assert response.status_code == 404


def test_uploaded_template_must_actually_be_a_docx(client):
    response = client.post(
        "/templates/upload",
        data={"template_id": "fake_letterhead", "label_fr": "Faux"},
        files={"file": ("letterhead.docx", b"this is not a zip", "application/octet-stream")},
    )
    assert response.status_code == 422


# ---- rendering -----------------------------------------------------------


def test_docx_render_contains_the_selected_data(client, document):
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "docx", "document": document}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "docx"
    assert body["size_bytes"] > 5000

    downloaded = client.get(body["download_url"])
    assert downloaded.status_code == 200
    xml = _docx_text(downloaded.content)
    for expected in (
        "BENALI",
        "CHU-2026-00412",
        "Méningiome frontal",
        "Diagnostic neurochirurgical",
        "Corrélation radiologique",
        "Constantes",
        "IRM cérébrale 14/08/2026",
        "Dr. Amina Kaci",
    ):
        assert expected in xml, f"missing {expected!r} from the rendered document"


def test_units_and_booleans_are_formatted_per_language(client, document):
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "html", "document": document}
    )
    html = client.get(response.json()["preview_url"]).text
    assert "32 mm" in html
    assert "Non" in html  # boolean false, rendered in French


def test_empty_fields_are_hidden_by_default_and_shown_on_request(client, document):
    hidden = client.get(
        client.post(
            "/render",
            json={"template": "generic_clinical", "format": "html", "document": document},
        ).json()["preview_url"]
    ).text
    assert "Téléphone" not in hidden

    document["options"]["show_empty_fields"] = True
    shown = client.get(
        client.post(
            "/render",
            json={"template": "generic_clinical", "format": "html", "document": document},
        ).json()["preview_url"]
    ).text
    assert "Téléphone" in shown
    assert "Non renseigné" in shown


@pytest.mark.parametrize(
    "language,marker,direction",
    [
        ("fr", "Généré le", "ltr"),
        ("en", "Generated on", "ltr"),
        ("ar", "تاريخ الإصدار", "rtl"),
    ],
)
def test_all_three_languages_render_with_the_right_direction(
    client, document, language, marker, direction
):
    document["language"] = language
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "html", "document": document}
    )
    assert response.status_code == 200
    html = client.get(response.json()["preview_url"]).text
    assert f'dir="{direction}"' in html
    assert marker in html


def test_arabic_docx_sets_rtl_and_a_complex_script_font(client, document):
    document["language"] = "ar"
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "docx", "document": document}
    )
    xml = _docx_text(client.get(response.json()["download_url"]).content)
    assert "<w:bidi" in xml
    assert "<w:rtl" in xml
    assert 'w:cs="Arial"' in xml


def test_a_document_with_no_sections_still_renders(client):
    response = client.post(
        "/render",
        json={
            "template": "generic_clinical",
            "format": "html",
            "document": {"patient": {"family_name": "X", "given_name": "Y"}, "sections": []},
        },
    )
    assert response.status_code == 200
    assert "Aucune donnée disponible" in client.get(response.json()["preview_url"]).text


def test_preview_is_always_available_even_without_libreoffice(client, document):
    """
    The portability guarantee: preview must not depend on LibreOffice. On a
    host with it the preview is a PDF, without it an HTML rendition - but
    `preview_url` is populated either way.
    """
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "docx", "document": document}
    )
    body = response.json()
    assert body["preview_url"] is not None
    assert body["preview_format"] in {"pdf", "html"}
    assert client.get(body["preview_url"]).status_code == 200


def test_pdf_request_degrades_gracefully_when_libreoffice_is_missing(client, document):
    from app import renderer

    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "pdf", "document": document}
    )
    assert response.status_code == 200
    body = response.json()
    if renderer.pdf_available():
        assert body["format"] == "pdf"
        assert not body["warnings"]
    else:
        assert body["format"] == "docx"
        assert any("LibreOffice" in w for w in body["warnings"])


# ---- legacy v1 contract --------------------------------------------------


def test_v1_imaging_payload_still_renders(client):
    response = client.post(
        "/render",
        json={
            "template": "chu_blida_imaging",
            "format": "html",
            "data": {
                "patient": {"family_name": "HADDAD", "given_name": "Sofiane"},
                "author": {"full_name": "Dr. Karim Belkacem"},
                "study": {"uid": "1.2.840.10008.1", "modality": "CT", "date": "01/08/2026"},
                "observation": {"text": "Hématome sous-dural aigu."},
            },
        },
    )
    assert response.status_code == 200
    html = client.get(response.json()["preview_url"]).text
    assert "Hématome sous-dural aigu." in html
    assert "1.2.840.10008.1" in html


def test_v1_neuro_payload_still_renders(client):
    response = client.post(
        "/render",
        json={
            "template": "chu_blida_neuro",
            "format": "html",
            "data": {
                "patient": {"family_name": "ZIANI", "given_name": "Lila"},
                "author": {"full_name": "Dr. N. Saadi"},
                "summary": {"text": "Patiente stable.", "gcs": "15"},
            },
        },
    )
    assert response.status_code == 200
    html = client.get(response.json()["preview_url"]).text
    assert "Patiente stable." in html


def test_render_without_document_or_data_is_rejected(client):
    response = client.post("/render", json={"template": "generic_clinical"})
    assert response.status_code == 422


# ---- artifact handling & hardening ---------------------------------------


def test_artifact_ids_are_opaque_and_paths_cannot_be_traversed(client, document):
    """
    v1 exposed `GET /download?path=...`, an arbitrary-file-read. Downloads now
    resolve an opaque id, and anything that is not a 32-hex id is refused
    before it ever touches the filesystem.
    """
    for candidate in (
        "../../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "not-a-real-id",
        "0" * 31,
        "/etc/passwd",
    ):
        response = client.get(f"/artifacts/{candidate}/download")
        assert response.status_code in (404, 400, 405), candidate
        assert b"root:" not in response.content


def test_artifact_can_be_deleted_immediately_after_download(client, document):
    artifact_id = client.post(
        "/render", json={"template": "generic_clinical", "document": document}
    ).json()["artifact_id"]

    assert client.get(f"/artifacts/{artifact_id}/download").status_code == 200
    assert client.delete(f"/artifacts/{artifact_id}").json()["deleted"] is True
    assert client.get(f"/artifacts/{artifact_id}/download").status_code == 404


def test_expired_artifacts_are_swept(client, document, monkeypatch):
    from app import artifacts

    artifact_id = client.post(
        "/render", json={"template": "generic_clinical", "document": document}
    ).json()["artifact_id"]

    # Rewind the recorded expiry rather than sleeping out the real TTL.
    import json
    from datetime import datetime, timedelta, timezone

    manifest = artifacts.settings.output_dir / artifact_id / "artifact.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    manifest.write_text(json.dumps(body), encoding="utf-8")

    assert artifacts.sweep_expired() >= 1
    assert client.get(f"/artifacts/{artifact_id}/download").status_code == 404


def test_filename_hint_is_sanitised(client, document):
    response = client.post(
        "/render",
        json={
            "template": "generic_clinical",
            "document": document,
            "filename_hint": "../../etc/Rapport Médical #1",
        },
    )
    filename = response.json()["filename"]
    assert "/" not in filename and "\\" not in filename and ".." not in filename
    assert filename.endswith(".docx")


def test_preview_response_is_not_cacheable(client, document):
    response = client.post(
        "/render", json={"template": "generic_clinical", "format": "html", "document": document}
    )
    preview = client.get(response.json()["preview_url"])
    assert "no-store" in preview.headers.get("cache-control", "")
    assert preview.headers.get("x-content-type-options") == "nosniff"
