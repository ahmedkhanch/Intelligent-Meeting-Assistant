"""HubSpot Notes — POST /crm/v3/objects/notes

Creates a note on the contact with the full PV content.

Requires scope: crm.objects.notes.write
"""

import logging

from app.routing.hubspot._timestamps import iso_to_millis
from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)


async def create_note(pv: dict, contact_id: str | None = None) -> dict:
    """Post the full PV as a HubSpot note, optionally attached to a contact."""
    call_date = pv.get("call_date", "")
    body: dict = {
        "properties": {
            "hs_note_body": _format_note_body(pv),
            "hs_timestamp": iso_to_millis(call_date) if call_date else "",
        }
    }
    if contact_id:
        body["associations"] = [
            {
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": 202,  # Note → Contact
                    }
                ],
                "to": {"id": contact_id},
            }
        ]

    logger.info("Creating HubSpot note for PV %s", pv.get("pv_id"))
    result = await hubspot_client.post("/crm/v3/objects/notes", body)
    logger.info("HubSpot note created: %s", result.get("id"))
    return result


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


def _format_note_body(pv: dict) -> str:
    """Format the PV as a rich note body, including caller intel."""
    lines = [
        f"📞 PROCÈS-VERBAL — {pv.get('call_type', '')}",
        f"",
        f"📋 Sujet : {pv.get('subject', '')}",
        f"📅 Date : {pv.get('call_date', '')}",
        f"",
        f"👥 PARTICIPANTS",
        _person_line(pv.get("left", {})),
        _person_line(pv.get("right", {})),
    ]
    for p in pv.get("additional_participants", []):
        if isinstance(p, dict):
            lines.append(_person_line(p))
    lines += [
        f"",
        f"📝 COMPTE RENDU",
        f"{pv.get('compte_rendu', '')}",
        f"",
    ]

    actions = pv.get("actions", [])
    if actions:
        lines.append("✅ ACTIONS")
        for a in actions:
            deadline = a.get("deadline", "—")
            lines.append(f"  □ {a['title']} → {a['owner']} (deadline: {deadline})")

    if pv.get("meeting_created"):
        lines.append(f"")
        lines.append(f"📅 Réunion planifiée : {pv.get('meeting_datetime', '')}")

    return "\n".join(lines)
