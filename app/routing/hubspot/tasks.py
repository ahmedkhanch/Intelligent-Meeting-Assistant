"""HubSpot Tasks — POST /crm/v3/objects/tasks

Creates individual HubSpot tasks for each action item extracted from the call.

Requires scope: crm.objects.tasks.write
"""

import logging

from app.routing.hubspot._timestamps import iso_to_millis
from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)


async def create_tasks(pv: dict) -> list[dict]:
    """Create a HubSpot task for each action item in the PV.

    Only called for commercial calls.
    """
    call_date = pv.get("call_date", "")

    results = []
    for action in pv.get("actions", []):
        body = {
            "properties": {
                "hs_task_body": action["title"],
                "hs_task_subject": action["title"],
                "hs_task_status": "NOT_STARTED",
                "hs_task_priority": "MEDIUM",
                "hs_timestamp": iso_to_millis(call_date) if call_date else "",
            }
        }
        # Add deadline if present — HubSpot expects [millis, ...]
        if action.get("deadline"):
            body["properties"]["hs_task_reminders"] = iso_to_millis(action["deadline"])

        logger.info("Creating HubSpot task: %s → %s", action["title"], action["owner"])
        result = await hubspot_client.post("/crm/v3/objects/tasks", body)
        results.append(result)

    logger.info("Created %d HubSpot tasks", len(results))
    return results
