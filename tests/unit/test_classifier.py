"""Tests for the classifier — a thin validation layer over the LLM call_type."""

from app.agent.classifier import VALID_CALL_TYPES, classify, validate


def test_validates_commercial_passthrough():
    assert validate("#appel-commercial") == "#appel-commercial"


def test_validates_tech_passthrough():
    assert validate("#appel-tech") == "#appel-tech"


def test_strips_whitespace():
    assert validate("  #appel-tech  ") == "#appel-tech"


def test_defaults_to_commercial_on_none():
    assert validate(None) == "#appel-commercial"


def test_defaults_to_commercial_on_empty_string():
    assert validate("") == "#appel-commercial"


def test_defaults_to_commercial_on_garbage():
    assert validate("not-a-real-type") == "#appel-commercial"


def test_classify_is_an_alias_for_validate():
    assert classify("#appel-tech") == "#appel-tech"
    assert classify("junk") == "#appel-commercial"


def test_valid_call_types_constant():
    assert VALID_CALL_TYPES == {"#appel-commercial", "#appel-tech"}
