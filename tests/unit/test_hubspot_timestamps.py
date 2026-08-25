"""Tests for the HubSpot timestamp conversion helpers."""

from datetime import date

from app.routing.hubspot._timestamps import date_to_millis, iso_to_millis


def test_iso_to_millis_epoch():
    assert iso_to_millis("1970-01-01T00:00:00Z") == 0


def test_iso_to_millis_naive_with_z():
    assert iso_to_millis("2026-06-22T10:00:00Z") == 1782122400000


def test_iso_to_millis_with_positive_offset():
    # 10:00+01:00 == 09:00 UTC
    assert iso_to_millis("2026-06-22T10:00:00+01:00") == 1782118800000


def test_iso_to_millis_date_only_is_midnight_utc():
    assert iso_to_millis("2026-06-22") == 1782086400000


def test_iso_to_millis_date_only_matches_explicit_midnight():
    assert iso_to_millis("2026-06-22") == iso_to_millis("2026-06-22T00:00:00Z")


def test_iso_to_millis_strips_whitespace():
    assert iso_to_millis("  1970-01-01T00:00:00Z  ") == 0


def test_date_to_millis_epoch():
    assert date_to_millis(date(1970, 1, 1)) == 0


def test_date_to_millis_matches_iso_date_only():
    assert date_to_millis(date(2026, 6, 22)) == iso_to_millis("2026-06-22")
