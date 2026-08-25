"""Integration tests for the FastAPI endpoints.

Uses httpx's ASGITransport to exercise the real app in-process (no network).
The summarizer is stubbed so no DeepSeek call is made.
"""

import httpx
import pytest
from httpx import ASGITransport

from app import fallback_store
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_call_start_returns_session(client):
    payload = {
        "left": {"name": "Ahmed", "phone_number": "1", "role": "AM", "side": "left"},
        "right": {"name": "Mehdi", "phone_number": "2", "role": "Client", "side": "right"},
        "subject": "Test",
    }
    resp = await client.post("/api/call/start", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["session_id"]
    assert data["subject"] == "Test"


async def test_call_process_requires_transcript(client):
    resp = await client.post("/api/call/process", json={})
    assert resp.status_code == 400
    assert "transcript" in resp.json()["detail"]


async def test_call_process_full_pipeline(client, commercial_pv, monkeypatch):
    async def fake_summarize(transcript, call_date=None, model=None):
        return commercial_pv

    monkeypatch.setattr("app.main.summarize", fake_summarize)

    resp = await client.post(
        "/api/call/process",
        json={"transcript": "[00:00:00] Ahmed : Bonjour", "session_id": "s-1"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["session_id"] == "s-1"
    assert data["pv"]["call_type"] == "#appel-commercial"
    # Actions got enriched by the extractor.
    assert data["pv"]["actions"]
    assert data["routing"]["destination"] == "hubspot"


async def test_fallback_pvs_endpoints(client, tech_pv, fallback_store_tmp):
    await fallback_store.save_pv(tech_pv)

    # List
    resp = await client.get("/api/fallback/pvs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["pvs"][0]["pv_id"] == "pv-tech-1"

    # Get one
    resp = await client.get("/api/fallback/pvs/pv-tech-1")
    assert resp.status_code == 200
    assert resp.json()["subject"] == tech_pv["subject"]

    # Missing → 404
    resp = await client.get("/api/fallback/pvs/nope")
    assert resp.status_code == 404

    # Todos
    resp = await client.get("/api/fallback/todos")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    # Clear
    resp = await client.delete("/api/fallback/pvs")
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1
