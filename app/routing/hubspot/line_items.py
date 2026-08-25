"""HubSpot Line Items — turn call actions into structured deal items.

Each action extracted from the PV becomes a line item on the deal,
visible in HubSpot's deal view as structured rows.

Endpoint: POST /crm/v3/objects/line_items
Scope:    crm.objects.line_items.write
"""

import logging

from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)


async def create_line_items_from_actions(
    pv: dict,
    deal_id: str,
) -> list[dict]:
    """Create a line item for each action and associate with the deal.

    Args:
        pv: The procès-verbal dict containing the actions list.
        deal_id: The HubSpot deal to associate line items with.

    Returns:
        List of created line item dicts.
    """
    actions = pv.get("actions", [])
    if not actions:
        logger.info("No actions to convert to line items")
        return []

    results: list[dict] = []
    for action in actions:
        title = action.get("title", "Action sans titre")
        owner = action.get("owner", "—")
        deadline = action.get("deadline", "—")
        difficulty = action.get("difficulty") or "—"

        body: dict = {
            "properties": {
                "name": title,
                "description": (
                    f"👤 Owner: {owner}\n"
                    f"📅 Deadline: {deadline}\n"
                    f"📊 Difficulty: {difficulty}"
                ),
                "quantity": "1",
            },
        }

        logger.info("Creating line item: '%s' on deal %s", title, deal_id)
        try:
            result = await hubspot_client.post("/crm/v3/objects/line_items", body)
            line_item_id = result.get("id")

            # Associate deal → line item (type 19 is Deal→LineItem, not the reverse)
            await hubspot_client.put(
                f"/crm/v3/objects/deals/{deal_id}/associations/line_items/{line_item_id}/deal_to_line_item"
            )
            results.append(result)
            logger.info("Line item created + associated: %s", line_item_id)
        except Exception:
            logger.error("Failed to create line item '%s'", title, exc_info=True)

    logger.info("Created %d/%d line items on deal %s", len(results), len(actions), deal_id)
    return results
