"""Tests for HubSpot note formatting & creation."""

from app.routing.hubspot.notes import _format_note_body, create_note


def test_format_note_body_includes_header_and_participants(commercial_pv):
    body = _format_note_body(commercial_pv)
    assert "PROCÈS-VERBAL" in body
    assert "Partenariat Q3 — Relyance Agency" in body
    assert "Ahmed" in body
    assert "Mehdi Trabelsi" in body


def test_format_note_body_lists_actions(commercial_pv):
    body = _format_note_body(commercial_pv)
    assert "✅ ACTIONS" in body
    assert "Envoyer la proposition révisée" in body


def test_format_note_body_includes_meeting(commercial_pv):
    body = _format_note_body(commercial_pv)
    assert "Réunion planifiée" in body


def test_format_note_body_no_meeting_line_when_absent(tech_pv):
    pv = dict(tech_pv, meeting_created=False)
    body = _format_note_body(pv)
    assert "Réunion planifiée" not in body


async def test_create_note_posts(commercial_pv, monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append((path, body))
        return {"id": "note-1"}

    monkeypatch.setattr("app.routing.hubspot.notes.hubspot_client.post", fake_post)

    result = await create_note(commercial_pv)

    assert result["id"] == "note-1"
    path, body = calls[0]
    assert path == "/crm/v3/objects/notes"
    assert body["properties"]["hs_note_body"]
