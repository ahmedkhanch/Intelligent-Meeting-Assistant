"""HubSpot Meetings — POST /crm/v3/objects/meetings

Schedules a follow-up meeting if one was detected during the call.

Requires scope: crm.objects.meetings.write
"""

import logging

from app.routing.hubspot._timestamps import iso_to_millis
from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)

DEFAULT_MEETING_DURATION_MS = 3_600_000  # 1 hour


async def create_meeting(pv: dict) -> dict | None:
    """Create a HubSpot meeting for the follow-up detected in the call.

    Returns None if no meeting was scheduled.
    """
    if not pv.get("meeting_created") or not pv.get("meeting_datetime"):
        logger.info("No meeting to create — skipping")
        return None

    meeting_time = pv["meeting_datetime"]
    start_millis = iso_to_millis(meeting_time)

    body = {
        "properties": {
            "hs_timestamp": start_millis,  # Required by HubSpot
            "hs_meeting_title": pv.get("subject", "Follow-up call"),
            "hs_meeting_start_time": start_millis,
            "hs_meeting_end_time": start_millis + DEFAULT_MEETING_DURATION_MS,
            "hs_meeting_body": pv.get("compte_rendu", "")[:500],
            "hs_internal_meeting_notes": (
                f"Call type: {pv.get('call_type', '')}\n"
                f"Subject: {pv.get('subject', '')}"
            ),
        }
    }

    logger.info("Creating HubSpot meeting for %s", meeting_time)
    result = await hubspot_client.post("/crm/v3/objects/meetings", body)
    logger.info("HubSpot meeting created: %s", result.get("id"))
    return result
