"""Timestamp conversion helpers for HubSpot API.

HubSpot CRM v3 requires date/time values as Unix timestamps in MILLISECONDS.
This module converts ISO-8601 strings to the format HubSpot expects.
"""

import calendar
from datetime import date, datetime, timezone


def iso_to_millis(iso_str: str) -> int:
    """Convert an ISO-8601 datetime string to Unix milliseconds.

    Handles:
        "2026-06-22T10:00:00"          → 1750586400000
        "2026-06-22T10:00:00Z"         → 1750586400000
        "2026-06-22T10:00:00+01:00"    → 1750582800000
        "2026-06-22"                   → 1750550400000 (midnight UTC)
    """
    s = iso_str.strip()
    if "T" not in s:
        # Date-only → midnight UTC
        s += "T00:00:00Z"
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return int(calendar.timegm(dt.utctimetuple()) * 1000)


def date_to_millis(d: date) -> int:
    """Convert a datetime.date to Unix milliseconds (midnight UTC)."""
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)
