"""Router — one call, one destination.

Reads call_type from the PV and dispatches to HubSpot or Ora Studio.
Never routes to both.

Commercial calls → HubSpot:
  1. Resolve owner       (crm.objects.owners.read)
  2. Find/create contact  (crm.objects.contacts.*)
  3. Create deal          (crm.objects.deals.write)
  4. Create line items    (crm.objects.line_items.write)
  5. Create appointment   (crm.objects.appointments.write)

Tech calls → Ora Studio: todo list + optional MCP agenda meeting.
When Ora Studio is unavailable (mock mode), todos land in the fallback store
and are displayed by the Next.js fallback UI.
"""

import logging

import httpx

from app.config import settings
from app.routing.hubspot import appointments, contacts, deals, line_items, notes, owners
from app.routing.ora_studio import todo as ora_todo
from app.mcp import agenda as mcp_agenda
from app import fallback_store

logger = logging.getLogger(__name__)


async def route(pv: dict) -> dict:
    """Dispatch a PV to the correct destination based on call_type.

    Returns a routing summary dict.
    """
    call_type = pv.get("call_type", "")

    if call_type == "#appel-commercial":
        return await _route_commercial(pv)
    elif call_type == "#appel-tech":
        return await _route_tech(pv)
    else:
        logger.warning("Unknown call_type '%s' — cannot route", call_type)
        return {"status": "unrouted", "reason": f"Unknown call_type: {call_type}"}


async def _route_commercial(pv: dict) -> dict:
    """Route to HubSpot with the full commercial pipeline.

    1. Resolve owner      — match PV owner names to HubSpot user IDs
    2. Find/create contact — ensure the call participant exists
    3. Create deal         — store PV as a Deal with full content
    4. Create line items   — turn each action into a structured line item
    5. Create appointment  — schedule meeting if one was detected
    """
    result = {"status": "ok", "destination": "hubspot", "operations": []}
    contact_id: str | None = None
    deal_id: str | None = None

    # ── 1. Resolve owner ───────────────────────────────────────────
    owner_id: str | None = None
    left = pv.get("left", {})
    owner_name = left.get("name", "")
    if owner_name:
        try:
            owner_id = await owners.resolve_owner_id(owner_name)
            if owner_id:
                result["operations"].append(f"owner_resolved: {owner_name} → {owner_id}")
            else:
                result["operations"].append(f"owner_not_found: {owner_name}")
        except Exception as e:
            logger.error("Owner lookup failed: %s", _format_error(e))
            result["operations"].append(f"owner_lookup_failed: {e}")

    # ── 2. Resolve contact ─────────────────────────────────────────
    try:
        contact_id = await contacts.find_or_create_contact(pv)
        if contact_id:
            result["operations"].append(f"contact_resolved: {contact_id}")
        else:
            result["operations"].append("contact_skipped: no identifiable person")
    except Exception as e:
        logger.error("Contact resolution failed: %s", _format_error(e))
        result["operations"].append(f"contact_failed: {e}")

    # ── 2b. Resolve additional external participants ────────────────
    additional_contact_ids: list[str] = []
    try:
        additional = await contacts.create_contacts_for_additional_participants(pv)
        for name, cid in additional:
            additional_contact_ids.append(cid)
            result["operations"].append(f"additional_contact_resolved: {name} → {cid}")
    except Exception as e:
        logger.error("Additional contact resolution failed: %s", _format_error(e))
        result["operations"].append(f"additional_contacts_failed: {e}")

    # ── 2c. Create note — the full PV summary, attached to the contact ──
    try:
        note = await notes.create_note(pv, contact_id=contact_id)
        result["operations"].append(f"note_created: {note.get('id')}")
    except Exception as e:
        logger.error("Note creation failed: %s", _format_error(e))
        result["operations"].append(f"note_failed: {e}")

    # ── 3. Create deal ─────────────────────────────────────────────
    try:
        deal = await deals.create_deal_from_pv(
            pv,
            contact_id=contact_id,
            owner_id=owner_id,
            additional_contact_ids=additional_contact_ids,
        )
        deal_id = deal.get("id")
        result["operations"].append(f"deal_created: {deal_id}")
    except Exception as e:
        logger.error("Deal creation failed: %s", _format_error(e))
        result["operations"].append(f"deal_failed: {e}")
        return result  # Can't continue without a deal

    # ── 4. Create line items ───────────────────────────────────────
    try:
        items = await line_items.create_line_items_from_actions(pv, deal_id)
        if items:
            result["operations"].append(f"line_items_created: {len(items)}")
        else:
            result["operations"].append("line_items_skipped: no actions")
    except Exception as e:
        logger.error("Line item creation failed: %s", _format_error(e))
        result["operations"].append(f"line_items_failed: {e}")

    # ── 5. Create appointment ──────────────────────────────────────
    try:
        appointment = await appointments.create_appointment(
            pv, contact_id=contact_id, deal_id=deal_id
        )
        if appointment:
            result["operations"].append(f"appointment_created: {appointment.get('id')}")
        else:
            result["operations"].append("appointment_skipped: no meeting scheduled")
    except Exception as e:
        logger.error("Appointment creation failed: %s", _format_error(e))
        result["operations"].append(f"appointment_failed: {e}")

    logger.info("Commercial routing complete: %s", result)
    return result


async def _route_tech(pv: dict) -> dict:
    """Route to Ora Studio: todo list + optional meeting via MCP agenda.

    When Ora Studio is unavailable (no API key / mock mode), PVs are saved
    to the local fallback store and displayed in the Next.js fallback UI.
    """
    ora_available = bool(settings.ora_studio_api_key)

    if ora_available:
        # ── Live Ora Studio ──────────────────────────────────────────
        result = {"status": "ok", "destination": "ora_studio", "operations": []}
        try:
            await ora_todo.post_todo(pv)
            result["operations"].append("todo_posted")
        except Exception as e:
            logger.error("Failed to post todo to Ora Studio: %s", _format_error(e))
            result["operations"].append(f"todo_failed: {e}")
    else:
        # ── Fallback: local store → Next.js UI ───────────────────────
        result = {"status": "ok", "destination": "fallback_ui", "operations": []}
        try:
            pv_id = await fallback_store.save_pv(pv)
            result["operations"].append(f"fallback_stored: {pv_id}")
        except Exception as e:
            logger.error("Failed to save PV to fallback store: %s", _format_error(e))
            result["operations"].append(f"fallback_failed: {e}")

    if pv.get("meeting_created"):
        try:
            await mcp_agenda.create_rdv(pv)
            result["operations"].append("rdv_created")
        except Exception as e:
            logger.error("Failed to create RDV via MCP agenda: %s", _format_error(e))
            result["operations"].append(f"rdv_failed: {e}")

    logger.info("Tech routing complete: %s", result)
    return result


def _format_error(e: Exception) -> str:
    """Extract the full error detail, including HubSpot response body."""
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.text
            return f"{e} — body: {body[:500]}"
        except Exception:
            pass
    return str(e)
