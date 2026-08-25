"""Integration tests for the router — one call, one destination.

These run the real routing code against the mock HubSpot / Ora Studio clients
(forced into mock mode by the ``_force_mock_mode`` autouse fixture).
"""

from app.agent.action_extractor import extract
from app.routing.router import route


async def test_route_commercial_to_hubspot(commercial_pv):
    pv = commercial_pv
    pv["actions"] = extract(pv)

    result = await route(pv)

    assert result["status"] == "ok"
    assert result["destination"] == "hubspot"

    ops = result["operations"]
    assert any(op.startswith("deal_created") for op in ops)
    assert any(op.startswith("contact_resolved") for op in ops)
    assert any(op.startswith("line_items_created") for op in ops)
    # A meeting was scheduled in the fixture → appointment should be created.
    assert any(op.startswith("appointment_created") for op in ops)


async def test_route_tech_to_fallback_store(tech_pv, fallback_store_tmp):
    pv = tech_pv
    pv["actions"] = extract(pv)

    result = await route(pv)

    assert result["status"] == "ok"
    assert result["destination"] == "fallback_ui"

    ops = result["operations"]
    assert any(op.startswith("fallback_stored") for op in ops)
    # Meeting scheduled → RDV created via the MCP agenda stub.
    assert any(op == "rdv_created" for op in ops)


async def test_route_tech_to_live_ora_studio(tech_pv, monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append((path, body))
        return {"status": "ok", "id": "todo-1"}

    # Force the "live" branch by faking a configured API key.
    monkeypatch.setattr("app.config.settings.ora_studio_api_key", "secret")
    monkeypatch.setattr("app.routing.ora_studio.client.ora_studio_client.post", fake_post)

    pv = tech_pv
    pv["actions"] = extract(pv)

    result = await route(pv)

    assert result["destination"] == "ora_studio"
    assert any(op == "todo_posted" for op in result["operations"])
    assert calls[0][0] == "/api/crm/tasks"


async def test_route_unknown_type_is_unrouted():
    result = await route({"call_type": "bogus"})
    assert result["status"] == "unrouted"


async def test_route_commercial_without_meeting_skips_appointment(commercial_pv):
    pv = dict(commercial_pv, meeting_created=False, meeting_datetime=None)
    pv["actions"] = extract(pv)

    result = await route(pv)

    assert result["destination"] == "hubspot"
    assert not any(op.startswith("appointment_created") for op in result["operations"])
    assert any(op.startswith("appointment_skipped") for op in result["operations"])
