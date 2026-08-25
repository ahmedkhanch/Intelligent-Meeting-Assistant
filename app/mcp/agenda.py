"""MCP Agenda Tool — creates RDVs (rendez-vous).

Reused component from last year's project.
Phase 1: Stub that logs the RDV creation.
"""

import logging

logger = logging.getLogger(__name__)


async def create_rdv(pv: dict) -> dict:
    """Create a rendez-vous from a PV that has a scheduled meeting.

    Only called for tech calls that have meeting_created=True.
    In Phase 1, this is a stub.
    """
    meeting_time = pv.get("meeting_datetime", "unknown")
    subject = pv.get("subject", "Follow-up")

    attendee_names = [
        pv.get("left", {}).get("name", "?"),
        pv.get("right", {}).get("name", "?"),
    ]
    attendee_names += [
        p.get("name", "?")
        for p in pv.get("additional_participants", [])
        if isinstance(p, dict)
    ]

    logger.info(
        "[MCP Agenda] Creating RDV: '%s' at %s with %s",
        subject,
        meeting_time,
        ", ".join(attendee_names),
    )

    # Phase 1: stub
    return {
        "status": "created",
        "rdv_id": "mock-rdv-id",
        "subject": subject,
        "datetime": meeting_time,
    }
