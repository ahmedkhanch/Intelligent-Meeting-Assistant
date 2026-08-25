"""Tests for the MCP agenda RDV stub."""

from app.mcp.agenda import create_rdv


async def test_create_rdv_returns_mock(tech_pv):
    result = await create_rdv(tech_pv)
    assert result["status"] == "created"
    assert result["rdv_id"] == "mock-rdv-id"
    assert result["subject"] == "Infra Ora CRM — environnements dev & prod"
    assert result["datetime"] == "2026-06-25T10:00:00Z"


async def test_create_rdv_defaults_when_fields_missing():
    result = await create_rdv({})
    assert result["rdv_id"] == "mock-rdv-id"
    assert result["subject"] == "Follow-up"
