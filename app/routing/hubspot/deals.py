"""HubSpot Deals — create & update.

Uses the CRM v3 Deals API (scope: crm.objects.deals.write / read).
"""

import logging
from datetime import date, datetime

from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────


def _best_closedate(pv: dict) -> str:
    """Pick the best close date for the deal.

    Precedence: meeting date → latest action deadline → today + 30 days.
    Returns an ISO date string (YYYY-MM-DD).
    """
    # Meeting date
    meeting_dt_str = pv.get("meeting_datetime", "")
    if meeting_dt_str:
        try:
            dt = datetime.fromisoformat(meeting_dt_str.replace("Z", "+00:00"))
            return dt.date().isoformat()
        except (ValueError, TypeError):
            pass

    # Latest action deadline
    deadlines: list[date] = []
    for action in pv.get("actions", []):
        dl = action.get("deadline", "")
        if dl:
            try:
                deadlines.append(date.fromisoformat(dl))
            except (ValueError, TypeError):
                pass
    if deadlines:
        return max(deadlines).isoformat()

    # Fallback: 30 days from now
    from datetime import date as _date, timedelta
    return (_date.today() + timedelta(days=30)).isoformat()


def _person_line(person: dict) -> str:
    """Format one participant as ``👤 Name — Role · ☎ phone``."""
    name = person.get("name", "?") or "?"
    role = person.get("role", "")
    phone = person.get("phone_number", "")
    line = f"👤 {name}"
    if role:
        line += f" — {role}"
    if phone:
        line += f" · ☎ {phone}"
    return line


def _format_deal_description(pv: dict) -> str:
    """Build a rich-text deal description from the PV."""
    lines = [
        f"📞 APPEL {pv.get('call_type', '').upper()}",
        "",
        f"📋 Sujet : {pv.get('subject', '')}",
        f"📅 Date de l'appel : {pv.get('call_date', '')}",
        "",
        f"👥 PARTICIPANTS",
        _person_line(pv.get("left", {})),
        _person_line(pv.get("right", {})),
    ]
    for participant in pv.get("additional_participants", []):
        if isinstance(participant, dict):
            lines.append(_person_line(participant))
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📝 COMPTE RENDU",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        pv.get("compte_rendu", ""),
    ]

    actions = pv.get("actions", [])
    if actions:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("✅ ACTIONS À FAIRE")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for i, a in enumerate(actions, 1):
            deadline = a.get("deadline", "—")
            difficulty = a.get("difficulty") or "—"
            lines.append(f"  {i}. [{difficulty}] {a['title']}")
            lines.append(f"     → {a['owner']}  |  deadline: {deadline}")

    if pv.get("meeting_created"):
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📅 RÉUNION PLANIFIÉE")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"  Date : {pv.get('meeting_datetime', '')}")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────


async def create_deal_from_pv(
    pv: dict,
    contact_id: str | None = None,
    owner_id: str | None = None,
    additional_contact_ids: list[str] | None = None,
) -> dict:
    """Create a HubSpot Deal from the PV data.

    The deal carries the full PV content in its description and is
    optionally associated with a contact and assigned to an owner.

    Args:
        pv: The procès-verbal dict from the summarizer.
        contact_id: Optional HubSpot contact ID to associate (primary external).
        owner_id: Optional HubSpot owner/user ID for deal assignment.
        additional_contact_ids: Optional extra contact IDs (additional external
            participants) to associate with the deal.

    Returns:
        The created deal dict from HubSpot.
    """
    dealname = pv.get("subject", f"Appel {pv.get('call_date', '')}")

    body: dict = {
        "properties": {
            "dealname": dealname,
            "dealstage": "appointmentscheduled",
            "description": _format_deal_description(pv),
            "closedate": _best_closedate(pv),
        }
    }

    # Assign to HubSpot owner if resolved
    if owner_id:
        body["properties"]["hubspot_owner_id"] = owner_id

    # Associations — primary contact + any additional external participants.
    contact_ids = [cid for cid in ([contact_id] + (additional_contact_ids or [])) if cid]
    associations: list[dict] = []
    for cid in contact_ids:
        associations.append({
            "types": [
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 3,  # Deal → Contact
                }
            ],
            "to": {"id": cid},
        })
    if associations:
        body["associations"] = associations

    logger.info("Creating HubSpot deal: '%s' (owner: %s)", dealname, owner_id or "—")
    result = await hubspot_client.post("/crm/v3/objects/deals", body)
    logger.info("HubSpot deal created: %s", result.get("id"))
    return result


async def update_deal_stage(deal_id: str, stage: str) -> dict:
    """Update a deal's stage in HubSpot.

    Args:
        deal_id: The HubSpot deal ID.
        stage: The new deal stage (e.g. 'contractsent', 'closedwon').
    """
    body = {"properties": {"dealstage": stage}}

    logger.info("Updating deal %s → stage %s", deal_id, stage)
    result = await hubspot_client.patch(
        f"/crm/v3/objects/deals/{deal_id}",
        body,
    )
    logger.info("Deal updated: %s", result.get("id"))
    return result
