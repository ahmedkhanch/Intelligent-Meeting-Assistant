"""HubSpot Appointments — schedule meetings from call data.

Creates a HubSpot Meeting/Appointment object when the PV indicates a
follow-up meeting was scheduled during the call.

Endpoint: POST /crm/v3/objects/meetings
Scope:    crm.objects.appointments.write
"""

import logging

from app.routing.hubspot._timestamps import iso_to_millis
from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)

DEFAULT_DURATION_MS = 3_600_000  # 1 hour


async def create_appointment(
    pv: dict,
    contact_id: str | None = None,
    deal_id: str | None = None,
) -> dict | None:
    """Create a HubSpot appointment for a scheduled follow-up meeting.

    Args:
        pv: The procès-verbal dict.
        contact_id: Optional contact ID to associate with.
        deal_id: Optional deal ID to associate with.

    Returns:
        The created appointment dict, or None if no meeting was scheduled.
    """
    if not pv.get("meeting_created") or not pv.get("meeting_datetime"):
        logger.info("No meeting scheduled — skipping appointment creation")
        return None

    meeting_time = pv["meeting_datetime"]
    start_millis = iso_to_millis(meeting_time)

    body: dict = {
        "properties": {
            "hs_timestamp": start_millis,  # Required by HubSpot
            "hs_meeting_title": pv.get("subject", "Follow-up call"),
            "hs_meeting_start_time": start_millis,
            "hs_meeting_end_time": start_millis + DEFAULT_DURATION_MS,
            "hs_meeting_body": pv.get("compte_rendu", "")[:500],
            "hs_internal_meeting_notes": (
                f"Généré automatiquement depuis l'appel du {pv.get('call_date', '')}\n"
                f"Type: {pv.get('call_type', '')}\n"
                f"Sujet: {pv.get('subject', '')}"
            ),
        }
    }

    # Build associations list
    associations: list[dict] = []
    if contact_id:
        associations.append({
            "types": [
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 200,  # Meeting → Contact
                }
            ],
            "to": {"id": contact_id},
        })

    if associations:
        body["associations"] = associations

    logger.info("Creating HubSpot appointment for %s", meeting_time)
    result = await hubspot_client.post("/crm/v3/objects/meetings", body)
    logger.info("HubSpot appointment created: %s", result.get("id"))
    return result
