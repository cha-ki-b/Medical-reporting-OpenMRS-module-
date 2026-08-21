"""
The clinician's free-text observation.

Two properties matter and are both asserted here: it appears **verbatim** (no translation, no
reflow beyond the line breaks typed), and it appears **last** - after the sections and after
the imaging observations - because it is the author's closing word on everything above it.
"""

from __future__ import annotations

import io
import re
import zipfile


# The rendered element, not the bare class name: `doctor-note` also appears in the page's
# inline stylesheet, so a substring check on it is always true and proves nothing.
NOTE_BLOCK = '<div class="doctor-note">'

OBSERVATION = (
    "Patient vu ce matin, etat stable.\n"
    "Indication operatoire retenue apres discussion en RCP.\n"
    "Prevoir bilan pre-anesthesique."
)


def _docx_xml(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _render(client, document, fmt="html", template="generic_clinical"):
    response = client.post(
        "/render", json={"template": template, "format": fmt, "document": document}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_observation_appears_in_the_html(client, document):
    document["doctor_observation"] = OBSERVATION
    html = client.get(_render(client, document)["preview_url"]).text

    assert "Observations du m" in html            # the localised heading
    assert "Indication operatoire retenue" in html
    # Each typed line becomes its own paragraph rather than one run-on blob.
    assert html.count('<div class="doctor-note">') == 1
    assert "Prevoir bilan pre-anesthesique" in html


def test_the_observation_appears_in_the_docx(client, document):
    document["doctor_observation"] = OBSERVATION
    body = _render(client, document, fmt="docx")
    xml = _docx_xml(client.get(body["download_url"]).content)

    # DocxLayout upper-cases level-1 LTR headings, so match case-insensitively.
    assert "observations du m" in xml.lower()
    for line in OBSERVATION.splitlines():
        assert line in xml


def test_the_observation_is_the_last_thing_in_the_document(client, document):
    """
    Position is the requirement, not just presence: it must follow the imaging observations,
    which themselves follow every section.
    """
    document["doctor_observation"] = OBSERVATION
    html = client.get(_render(client, document)["preview_url"]).text

    diagnosis = html.index("Diagnostic neurochirurgical")
    imaging = html.index("IRM c")               # the imaging observations block
    note = html.index("Indication operatoire retenue")

    assert diagnosis < imaging < note


def test_the_heading_is_localised_but_the_text_is_not(client, document):
    """The heading is page furniture; the observation is the clinician's own words."""
    document["doctor_observation"] = OBSERVATION

    document["language"] = "en"
    english = client.get(_render(client, document)["preview_url"]).text
    assert "Doctor observations" in english
    assert "Indication operatoire retenue" in english

    document["language"] = "ar"
    arabic = client.get(_render(client, document)["preview_url"]).text
    assert "ملاحظات الطبيب" in arabic
    # Untranslated on purpose - it is reproduced exactly as typed.
    assert "Indication operatoire retenue" in arabic


def test_no_heading_when_there_is_no_observation(client, document):
    document.pop("doctor_observation", None)
    html = client.get(_render(client, document)["preview_url"]).text
    assert NOTE_BLOCK not in html


def test_a_whitespace_only_observation_is_treated_as_empty(client, document):
    document["doctor_observation"] = "   \n\t  \n "
    html = client.get(_render(client, document)["preview_url"]).text
    assert NOTE_BLOCK not in html


def test_an_observation_alone_still_produces_a_report(client):
    """An observation-only report must not fall back to the 'no data' placeholder."""
    response = client.post(
        "/render",
        json={
            "template": "generic_clinical",
            "format": "html",
            "document": {
                "patient": {"family_name": "SOLO", "given_name": "Test"},
                "sections": [],
                "doctor_observation": "Rien a signaler.",
            },
        },
    )
    assert response.status_code == 200
    html = client.get(response.json()["preview_url"]).text
    assert "Rien a signaler." in html
    assert "Aucune donn" not in html


def test_the_observation_is_html_escaped(client, document):
    """It is user input rendered into HTML; angle brackets must not become markup."""
    document["doctor_observation"] = "Risque <script>alert(1)</script> eleve"
    html = client.get(_render(client, document)["preview_url"]).text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_long_observations_survive_intact(client, document):
    paragraph = " ".join(f"phrase{i}" for i in range(400))
    document["doctor_observation"] = paragraph
    html = client.get(_render(client, document)["preview_url"]).text
    assert "phrase0" in html and "phrase399" in html
