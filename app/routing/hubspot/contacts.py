"""HubSpot Contacts — search & create.

Uses the CRM v3 Contacts API (scope: crm.objects.contacts.write / read).
"""

import logging

from app.routing.hubspot.client import hubspot_client

logger = logging.getLogger(__name__)


def _parse_name(full_name: str) -> tuple[str, str]:
    """Split a full name into (firstname, lastname).

    Returns ("Inconnu", "") if name is unknown.
    """
    if not full_name or full_name.lower() in ("inconnu", "?"):
        return "Inconnu", ""
    parts = full_name.strip().split(maxsplit=1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    return first, last


async def find_or_create_contact(pv: dict) -> str | None:
    """Find existing contact or create a new one from PV data.

    Strategy:
        1. Search by name (HubSpot search endpoint).
        2. If not found, create a new contact.
        3. Return the contact ID.

    Returns None if no usable identity is present in the PV.
    """
    right = pv.get("right", {})
    name = right.get("name", "")
    phone = right.get("phone_number", "")
    role = right.get("role", "")

    return await _find_or_create_by_name_phone(name, phone, role)


async def create_contacts_for_additional_participants(pv: dict) -> list[tuple[str, str]]:
    """Create (or find) HubSpot contacts for additional *external* participants.

    For multi-party meetings, the primary external contact lives in `right`.
    Every other external speaker (``side == "right"``) in
    ``additional_participants`` is resolved to a contact here so that nobody
    is silently dropped from the CRM.

    Returns:
        A list of ``(name, contact_id)`` tuples for each resolved contact.
    """
    created: list[tuple[str, str]] = []
    for participant in pv.get("additional_participants", []):
        if not isinstance(participant, dict):
            continue
        if participant.get("side") != "right":
            continue  # Ora-side team members are owners, not contacts
        name = participant.get("name", "")
        phone = participant.get("phone_number", "")
        role = participant.get("role", "")
        contact_id = await _find_or_create_by_name_phone(name, phone, role)
        if contact_id:
            created.append((name, contact_id))
    return created


async def _find_or_create_by_name_phone(name: str, phone: str, role: str = "") -> str | None:
    """Resolve a single name/phone/role to a HubSpot contact ID (search then create)."""
    firstname, lastname = _parse_name(name)

    # ── If we have no useful identifier, bail ──────────────────────
    if firstname == "Inconnu" and phone in ("inconnu", "", None):
        logger.warning("No identifiable contact info — skipping contact resolution")
        return None

    # ── Search by name ────────────────────────────────────────────
    contact_id = await _search_contact(firstname, lastname)
    if contact_id:
        logger.info("Found existing contact: %s (id: %s)", name, contact_id)
        return contact_id

    # ── Create new contact ────────────────────────────────────────
    logger.info("Contact '%s' not found — creating", name)
    body: dict[str, dict] = {
        "properties": {
            "firstname": firstname,
            "lastname": lastname,
        }
    }
    if phone and phone not in ("inconnu", ""):
        body["properties"]["phone"] = phone
    if role and role not in ("inconnu", ""):
        # HubSpot's standard property for job title / occupation.
        body["properties"]["jobtitle"] = role

    result = await hubspot_client.post("/crm/v3/objects/contacts", body)
    contact_id = result.get("id")
    logger.info("Contact created: %s (id: %s)", name, contact_id)
    return contact_id


async def _search_contact(firstname: str, lastname: str) -> str | None:
    """Search HubSpot for a contact by name.

    Returns the contact ID if found, None otherwise.
    """
    filters = []
    if firstname and firstname != "Inconnu":
        filters.append({
            "propertyName": "firstname",
            "operator": "EQ",
            "value": firstname,
        })
    if lastname:
        filters.append({
            "propertyName": "lastname",
            "operator": "EQ",
            "value": lastname,
        })

    if not filters:
        return None

    search_body = {
        "filterGroups": [{"filters": filters}],
        "limit": 1,
        "properties": ["firstname", "lastname"],
    }

    try:
        result = await hubspot_client.post("/crm/v3/objects/contacts/search", search_body)
        results = result.get("results", [])
        if results:
            return results[0]["id"]
    except Exception:
        logger.debug("Contact search failed — will create", exc_info=True)

    return None
