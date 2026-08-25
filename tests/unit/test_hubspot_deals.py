"""Tests for HubSpot deal creation helpers."""

from datetime import date, timedelta

from app.routing.hubspot.deals import (
    _best_closedate,
    _format_deal_description,
    create_deal_from_pv,
)


def test_best_closedate_prefers_meeting(commercial_pv):
    assert _best_closedate(commercial_pv) == "2026-06-23"


def test_best_closedate_uses_latest_deadline():
    pv = {
        "meeting_datetime": "",
        "actions": [
            {"deadline": "2026-06-20"},
            {"deadline": "2026-06-21"},
        ],
    }
    assert _best_closedate(pv) == "2026-06-21"


def test_best_closedate_falls_back_to_30_days():
    pv = {"meeting_datetime": "", "actions": []}
    expected = (date.today() + timedelta(days=30)).isoformat()
    assert _best_closedate(pv) == expected


def test_best_closedate_ignores_invalid_deadlines():
    pv = {
        "meeting_datetime": "",
        "actions": [{"deadline": "garbage"}, {"deadline": "2026-06-20"}],
    }
    assert _best_closedate(pv) == "2026-06-20"


def test_format_deal_description_includes_content(commercial_pv):
    text = _format_deal_description(commercial_pv)
    assert "Partenariat Q3 — Relyance Agency" in text
    assert "#APPEL-COMMERCIAL" in text
    assert "Discussion commerciale" in text
    assert "Envoyer la proposition révisée" in text
    assert "RÉUNION PLANIFIÉE" in text


async def test_create_deal_body(commercial_pv, monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append((path, body))
        return {"id": "deal-999"}

    monkeypatch.setattr("app.routing.hubspot.deals.hubspot_client.post", fake_post)

    result = await create_deal_from_pv(
        commercial_pv, contact_id="contact-1", owner_id="owner-1"
    )

    assert result["id"] == "deal-999"
    path, body = calls[0]
    assert path == "/crm/v3/objects/deals"

    props = body["properties"]
    assert props["dealname"] == "Partenariat Q3 — Relyance Agency"
    assert props["dealstage"] == "appointmentscheduled"
    assert props["closedate"] == "2026-06-23"
    assert props["hubspot_owner_id"] == "owner-1"
    assert body["associations"][0]["to"]["id"] == "contact-1"


async def test_create_deal_omits_owner_and_associations_when_absent(commercial_pv, monkeypatch):
    async def fake_post(path, body):
        return {"id": "deal-1", "properties": body, "_body": body}

    monkeypatch.setattr("app.routing.hubspot.deals.hubspot_client.post", fake_post)

    result = await create_deal_from_pv(commercial_pv)

    assert result["id"] == "deal-1"
    body = result["_body"]
    assert "hubspot_owner_id" not in body["properties"]
    assert "associations" not in body
