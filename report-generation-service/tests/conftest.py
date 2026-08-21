"""
Test fixtures.

Environment is set before `app.config` is imported, because Settings resolves
once at import time - importing the app first would bind the developer's real
output/template directories into the test run.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_TOKEN = "test-token-0123456789"


@pytest.fixture(scope="session")
def app_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("rgs")
    os.environ["MEDREPORT_RGS_TOKEN"] = TEST_TOKEN
    os.environ["MEDREPORT_TEMPLATES_DIR"] = str(root / "templates")
    os.environ["MEDREPORT_OUTPUT_DIR"] = str(root / "output")
    os.environ["MEDREPORT_CLEANUP_INTERVAL_SECONDS"] = "3600"

    for module in (
        "app.config",
        "app.security",
        "app.artifacts",
        "app.templates_registry",
        "app.renderer",
        "app.layout_docx",
        "app.layout_html",
        "app.main",
    ):
        if module in sys.modules:
            importlib.reload(sys.modules[module])
    return root


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        test_client.headers.update({"X-Medreport-Token": TEST_TOKEN})
        yield test_client


@pytest.fixture()
def document():
    """A representative use-case-2 payload: sets, sub-sets, records, images."""
    return {
        "language": "fr",
        "title": "Rapport médical complet",
        "subtitle": "Service de Neurochirurgie",
        "patient": {
            "family_name": "BENALI",
            "given_name": "Yacine",
            "birthdate": "12/04/1978",
            "age": "48",
            "gender": "M",
            "identifier": "CHU-2026-00412",
        },
        "author": {"full_name": "Dr. Amina Kaci", "role": "Neurochirurgien"},
        "sections": [
            {
                "id": "demographics",
                "title": "Données démographiques",
                "fields": [
                    {"key": "profession", "label": "Profession", "value": "Enseignant"},
                    {"key": "phone", "label": "Téléphone", "value": None},
                ],
            },
            {
                "id": "diagnosis",
                "title": "Diagnostic neurochirurgical",
                "fields": [
                    {"key": "diagnosis", "label": "Diagnostic", "value": "Méningiome frontal", "emphasis": True},
                    {"key": "laterality", "label": "Latéralité", "value": "Gauche"},
                    {"key": "size", "label": "Taille", "value": "32", "unit": "mm"},
                    {"key": "recurrence", "label": "Récidive", "value": "false", "type": "boolean"},
                    {"key": "who", "label": "Classification OMS", "value": "Grade I\nAtypies absentes", "type": "longtext"},
                ],
                "subsections": [
                    {
                        "id": "imaging_notes",
                        "title": "Corrélation radiologique",
                        "fields": [{"key": "irm", "label": "IRM", "value": "Prise de contraste homogène"}],
                    }
                ],
            },
            {
                "id": "vitals",
                "title": "Constantes",
                "records": [
                    {
                        "title": "10/08/2026",
                        "subtitle": "Consultation pré-opératoire",
                        "fields": [
                            {"key": "ta", "label": "Tension artérielle", "value": "13/8"},
                            {"key": "fc", "label": "Fréquence cardiaque", "value": "72", "unit": "bpm"},
                        ],
                    },
                    {
                        "title": "14/08/2026",
                        "fields": [{"key": "ta", "label": "Tension artérielle", "value": "12/7"}],
                    },
                ],
            },
        ],
        "image_observations": [
            {
                "image_label": "IRM cérébrale 14/08/2026",
                "study_uid": "1.2.840.113619.2.55.3.1234",
                "modality": "MR",
                "study_date": "14/08/2026",
                "author": "Dr. Amina Kaci",
                "text": "Lésion extra-axiale frontale gauche.\nPas d'engagement.",
            }
        ],
        "options": {"include_table_of_contents": True, "show_empty_fields": False},
    }
