"""Ora Studio Todo — POST /api/crm/tasks

Sends the extracted todo list to Ora Studio after a tech call.
"""

import logging

from app.routing.ora_studio.client import ora_studio_client

logger = logging.getLogger(__name__)


async def post_todo(pv: dict) -> dict:
    """Post the extracted todo list to Ora Studio.

    Only called for tech calls. Sends tasks with difficulty + model_hint
    so Ora Studio can route each task to the right AI model.
    """
    body = {
        "pv_id": pv.get("pv_id"),
        "call_date": pv.get("call_date"),
        "subject": pv.get("subject"),
        "participants": [
            pv.get("left", {}).get("name", "?"),
            pv.get("right", {}).get("name", "?"),
        ],
        "tasks": [
            {
                "title": t["title"],
                "owner": t["owner"],
                "difficulty": t.get("difficulty"),
                "model_hint": t.get("model_hint"),
                "deadline": t.get("deadline"),
            }
            for t in pv.get("actions", [])
        ],
        "meeting_created": pv.get("meeting_created", False),
        "meeting_datetime": pv.get("meeting_datetime"),
    }

    logger.info(
        "Posting todo list to Ora Studio: %d tasks → %s",
        len(body["tasks"]),
        [t["title"] for t in body["tasks"]],
    )
    result = await ora_studio_client.post("/api/crm/tasks", body)
    logger.info("Ora Studio todo list posted: %s", result.get("id"))
    return result
