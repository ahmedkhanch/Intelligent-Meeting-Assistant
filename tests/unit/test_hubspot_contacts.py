"""Tests for HubSpot contact resolution."""

import pytest

from app.routing.hubspot.contacts import _parse_name, find_or_create_contact


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [
        ("Mehdi Trabelsi", ("Mehdi", "Trabelsi")),
        ("Ahmed", ("Ahmed", "")),
        ("Inconnu", ("Inconnu", "")),
        ("inconnu", ("Inconnu", "")),
        ("?", ("Inconnu", "")),
        ("", ("Inconnu", "")),
        ("  Mehdi Trabelsi  ", ("Mehdi", "Trabelsi")),
    ],
)
def test_parse_name(full_name, expected):
    assert _parse_name(full_name) == expected


async def test_find_or_create_returns_none_without_identity():
    pv = {"right": {"name": "", "phone_number": ""}}
    assert await find_or_create_contact(pv) is None


async def test_find_or_create_returns_existing_contact(commercial_pv, monkeypatch):
    async def fake_post(path, body):
        if path.endswith("/search"):
            return {"results": [{"id": "existing-42"}]}
        return {"id": "should-not-create"}

    monkeypatch.setattr("app.routing.hubspot.contacts.hubspot_client.post", fake_post)
    assert await find_or_create_contact(commercial_pv) == "existing-42"


async def test_find_or_create_creates_contact(commercial_pv, monkeypatch):
    calls = []

    async def fake_post(path, body):
        calls.append((path, body))
        if path.endswith("/search"):
            return {"results": []}
        return {"id": "contact-123"}

    monkeypatch.setattr("app.routing.hubspot.contacts.hubspot_client.post", fake_post)

    contact_id = await find_or_create_contact(commercial_pv)

    assert contact_id == "contact-123"
    assert calls[0][0] == "/crm/v3/objects/contacts/search"
    assert calls[1][0] == "/crm/v3/objects/contacts"

    create_body = calls[1][1]
    assert create_body["properties"]["firstname"] == "Mehdi"
    assert create_body["properties"]["lastname"] == "Trabelsi"
    assert create_body["properties"]["phone"] == "+216 98 000 000"
