"""Integration tests for the multi-member WebSocket call path.

The transcription and routing are mocked (no network) so these stay hermetic;
we verify that per-member streams are merged into a labeled transcript and
that a PV is broadcast back over the member's own WebSocket.
"""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.ws import call_handler
from app.ws.session_manager import MeetingSession


# ── Fakes ────────────────────────────────────────────────────────────────


async def _fake_stream_transcribe(chunks, *, on_delta=None, on_segment=None, **kwargs):
    if on_segment:
        await on_segment("Bonjour à tous")
    return "Bonjour à tous"


def _fake_pv() -> dict:
    return {
        "call_type": "#appel-tech",
        "left": {"name": "Sami", "side": "left"},
        "right": {"name": "Oussema", "side": "right"},
        "subject": "Test",
        "compte_rendu": "ok",
        "actions": [],
        "meeting_created": False,
    }


async def _fake_summarize(transcript, **kwargs):
    return _fake_pv()


async def _fake_route(pv):
    return {"status": "ok", "destination": "fallback_ui"}


# ── Tests ────────────────────────────────────────────────────────────────


async def test_control_frames():
    session = MeetingSession(session_id="s1")
    # listen_start / listen_stop toggle agent listening (return an action)
    assert await call_handler._handle_control(session, json.dumps({"type": "listen_start"})) == "listen_start"
    assert await call_handler._handle_control(session, json.dumps({"type": "listen_stop"})) == "listen_stop"
    # audio_end is a legacy alias for listen_stop
    assert await call_handler._handle_control(session, json.dumps({"type": "audio_end"})) == "listen_stop"
    assert session.end_requested is False
    # end_call marks the call for finalization
    assert await call_handler._handle_control(session, json.dumps({"type": "end_call"})) == "end_call"
    assert session.end_requested is True
    # unknown / non-JSON frames are ignored (return None)
    assert await call_handler._handle_control(session, "not json") is None


async def test_finalize_reuses_last_draft_when_unchanged(monkeypatch):
    calls = {"summarize": 0}

    async def fake_summarize(transcript, **kwargs):
        calls["summarize"] += 1
        return _fake_pv()

    monkeypatch.setattr(call_handler, "summarize", fake_summarize)
    monkeypatch.setattr(call_handler, "route", _fake_route)

    session = MeetingSession(session_id="s1")
    session.attach("Sami", ws=None)
    session.add_text("Sami", "Bonjour")
    # Simulate an incremental draft that already ran on this exact transcript.
    session.last_draft_chars = len(session.build_transcript())
    session.last_draft_pv = {**_fake_pv(), "call_type": "#appel-tech", "actions": []}
    session.request_end()

    await call_handler._finalize(session)

    # The summarizer should NOT be called again — the draft is reused.
    assert calls["summarize"] == 0


async def test_finalize_builds_labeled_transcript(monkeypatch):
    captured = {}

    async def fake_summarize(transcript, **kwargs):
        captured["transcript"] = transcript
        return _fake_pv()

    monkeypatch.setattr(call_handler, "summarize", fake_summarize)
    monkeypatch.setattr(call_handler, "route", _fake_route)

    session = MeetingSession(session_id="s1")
    session.attach("Sami", ws=None)
    session.attach("Lina", ws=None)
    session.add_text("Sami", "Bonjour à tous")
    session.add_text("Lina", "Bonjour Sami")
    session.request_end()

    await call_handler._finalize(session)

    assert "Sami : Bonjour à tous" in captured["transcript"]
    assert "Lina : Bonjour Sami" in captured["transcript"]


def test_member_ws_route_returns_pv(monkeypatch):
    monkeypatch.setattr(call_handler, "stream_transcribe", _fake_stream_transcribe)
    monkeypatch.setattr(call_handler, "summarize", _fake_summarize)
    monkeypatch.setattr(call_handler, "route", _fake_route)

    client = TestClient(app)
    with client.websocket_connect("/ws/call/test-session/Sami") as ws:
        ws.send_text(json.dumps({"type": "listen_start"}))
        ws.send_text(json.dumps({"type": "end_call"}))

        result = None
        for _ in range(20):
            msg = ws.receive_json()
            if msg.get("type") in ("pv_result", "error"):
                result = msg
                break

        assert result is not None
        assert result["type"] == "pv_result"
        assert result["pv"]["left"]["name"] == "Sami"
