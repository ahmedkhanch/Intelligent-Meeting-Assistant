"""Shared fixtures for the CRM Vocal test suite.

The most important fixture here is ``_force_mock_mode`` — it guarantees that no
test ever touches a real HubSpot / Ora Studio / DeepSeek API, regardless of what
``.env`` contains. The production clients decide mock-vs-live at import time by
reading ``app.config.settings``, so we neutralize those flags before each test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import fallback_store

# ── Fixture data (raw summarizer output, pre-action-extraction) ────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_transcript(name: str) -> str:
    """Read a sample transcript fixture by filename."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture
def tech_transcript() -> str:
    return load_transcript("sample_transcript_tech.txt")


@pytest.fixture
def commercial_transcript() -> str:
    return load_transcript("sample_transcript_commercial.txt")


@pytest.fixture
def ambiguous_transcript() -> str:
    return load_transcript("sample_transcript_ambiguous.txt")


@pytest.fixture
def commercial_pv() -> dict:
    """A realistic commercial PV as returned by the summarizer."""
    return {
        "pv_id": "pv-commercial-1",
        "call_date": "2026-06-22",
        "call_type": "#appel-commercial",
        "left": {
            "name": "Ahmed",
            "phone_number": "+216 20 000 000",
            "role": "Account Manager",
            "side": "left",
        },
        "right": {
            "name": "Mehdi Trabelsi",
            "phone_number": "+216 98 000 000",
            "role": "Client — Relyance Agency",
            "side": "right",
        },
        "subject": "Partenariat Q3 — Relyance Agency",
        "compte_rendu": "Discussion commerciale autour du partenariat Q3.",
        "actions": [
            {
                "title": "Envoyer la proposition révisée",
                "owner": "Ahmed",
                "deadline": "2026-06-20",
                "difficulty": None,
            },
            {
                "title": "Préparer la documentation data handling",
                "owner": "kh",
                "deadline": "2026-06-21",
                "difficulty": None,
            },
        ],
        "meeting_created": True,
        "meeting_datetime": "2026-06-23T14:00:00Z",
    }


@pytest.fixture
def tech_pv() -> dict:
    """A realistic technical PV as returned by the summarizer."""
    return {
        "pv_id": "pv-tech-1",
        "call_date": "2026-06-22",
        "call_type": "#appel-tech",
        "left": {
            "name": "kh",
            "phone_number": "+216 20 111 111",
            "role": "CTO",
            "side": "left",
        },
        "right": {
            "name": "Oussema",
            "phone_number": "+216 98 111 111",
            "role": "DevOps",
            "side": "right",
        },
        "subject": "Infra Ora CRM — environnements dev & prod",
        "compte_rendu": "Point technique sur la mise en place des environnements.",
        "actions": [
            {
                "title": "Créer l'environnement dev sur GitLab",
                "owner": "Oussema",
                "deadline": "2026-06-26",
                "difficulty": "facile",
            },
            {
                "title": "Implémenter le endpoint POST /api/crm/tasks",
                "owner": "Oussema",
                "deadline": "2026-06-25",
                "difficulty": "difficile",
            },
        ],
        "meeting_created": True,
        "meeting_datetime": "2026-06-25T10:00:00Z",
    }


# ── Environment isolation ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _force_mock_mode(monkeypatch):
    """Force every external integration into mock/fallback mode.

    The app reads credentials from ``.env`` (which may contain real tokens), so
    we reset the relevant flags before each test to keep the suite hermetic and
    network-free. Any test that needs the *live* code path explicitly overrides
    the flag it cares about.
    """
    from app import fallback_store  # noqa: F401  (ensure module loaded)
    from app.config import settings
    from app.routing.hubspot import owners
    from app.routing.hubspot.client import hubspot_client
    from app.routing.ora_studio.client import ora_studio_client

    # Reset credentials so the singletons behave as mocks.
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(settings, "hubspot_access_token", "")
    monkeypatch.setattr(settings, "hubspot_client_id", "")
    monkeypatch.setattr(settings, "ora_studio_api_key", "")
    monkeypatch.setattr(hubspot_client, "_mock", True)
    monkeypatch.setattr(ora_studio_client, "_mock", True)

    # The owners module caches lookups in a module-level dict — clear between tests.
    owners._cache.clear()


@pytest.fixture
def fallback_store_tmp(tmp_path, monkeypatch):
    """Point the fallback store at an isolated temp file (no writes to ui-next/)."""
    store_path = tmp_path / "fallback_pvs.json"
    monkeypatch.setattr(fallback_store, "STORE_DIR", tmp_path)
    monkeypatch.setattr(fallback_store, "STORE_PATH", store_path)
    return store_path
