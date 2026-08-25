"""HubSpot Owners — resolve names to user IDs.

Uses GET /crm/v3/owners (scope: crm.objects.owners.read).
Results are cached per session to avoid redundant API calls.
"""

import logging

from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)

# ── Session cache ─────────────────────────────────────────────────────
_cache: dict[str, str | None] = {}


async def resolve_owner_id(name: str) -> str | None:
    """Look up a HubSpot owner/user ID by display name.

    The lookup is case-insensitive and matches on first name,
    last name, or full name. Results are cached in-memory.

    Args:
        name: A name string from the PV (e.g. "Ahmed", "kh").

    Returns:
        The HubSpot owner ID as a string, or None if not found.
    """
    name_lower = name.strip().lower()
    if not name_lower:
        return None

    # Cache hit
    if name_lower in _cache:
        cached = _cache[name_lower]
        if cached:
            logger.debug("Owner cache hit: %s → %s", name, cached)
        return cached

    # Fetch owners from HubSpot
    try:
        result = await hubspot_client.get("/crm/v3/owners")
        owners = result.get("results", [])
    except Exception:
        logger.warning("Failed to fetch HubSpot owners — caching as not found", exc_info=True)
        _cache[name_lower] = None
        return None

    # Search for matching owner
    for owner in owners:
        first = (owner.get("firstName") or "").strip().lower()
        last = (owner.get("lastName") or "").strip().lower()
        email = (owner.get("email") or "").strip().lower()
        owner_id = owner.get("id")

        # Match against first name, last name, full name, or email prefix
        if (
            name_lower == first
            or name_lower == last
            or name_lower == f"{first} {last}"
            or name_lower in email.split("@")[0]
        ):
            _cache[name_lower] = owner_id
            logger.info("Owner resolved: '%s' → %s (%s %s)", name, owner_id, first, last)
            return owner_id

    # Not found — cache the miss
    logger.info("Owner '%s' not found among %d HubSpot owners", name, len(owners))
    _cache[name_lower] = None
    return None
