"""Tests for the Ora Studio todo posting (payload mapping)."""

from app.routing.ora_studio.todo import post_todo


def _tech_pv_with_hints() -> dict:
    return {
        "pv_id": "pv-tech-1",
        "call_date": "2026-06-22",
        "subject": "Infra Ora CRM",
        "left": {"name": "kh"},
        "right": {"name": "Oussema"},
        "actions": [
            {
                "title": "Créer l'env dev",
                "owner": "Oussema",
                "difficulty": "facile",
                "model_hint": "gpt-4o-mini",
                "deadline": "2026-06-26",
            },
            {
                "title": "Implémenter endpoint",
                "owner": "Oussema",
                "difficulty": "difficile",
                "model_hint": "claude-sonnet-4-6",
                "deadline": "2026-06-25",
            },
        ],
        "meeting_created": True,
        "meeting_datetime": "2026-06-25T10:00:00Z",
    }


async def test_post_todo_maps_payload(monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append((path, body))
        return {"status": "ok", "id": "todo-1"}

    monkeypatch.setattr("app.routing.ora_studio.client.ora_studio_client.post", fake_post)

    result = await post_todo(_tech_pv_with_hints())

    assert result["id"] == "todo-1"
    path, body = calls[0]
    assert path == "/api/crm/tasks"

    assert body["pv_id"] == "pv-tech-1"
    assert body["subject"] == "Infra Ora CRM"
    assert body["participants"] == ["kh", "Oussema"]
    assert body["meeting_created"] is True

    tasks = body["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["difficulty"] == "facile"
    assert tasks[0]["model_hint"] == "gpt-4o-mini"
    assert tasks[1]["model_hint"] == "claude-sonnet-4-6"
