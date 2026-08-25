"""Tests for the summarizer's JSON parsing and prompt templates.

The actual DeepSeek call is exercised only via a mock in the integration tests;
here we cover the deterministic helpers.
"""

import pytest

from app.agent.summarizer import SYSTEM_PROMPT, USER_PROMPT, _parse_json


def test_parse_direct_json():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_inside_fenced_block():
    raw = '```json\n{"call_type": "#appel-tech", "subject": "s"}\n```'
    assert _parse_json(raw) == {"call_type": "#appel-tech", "subject": "s"}


def test_parse_json_fenced_block_without_language():
    raw = '```\n{"call_type": "#appel-commercial"}\n```'
    assert _parse_json(raw) == {"call_type": "#appel-commercial"}


def test_parse_json_surrounded_by_prose():
    raw = 'Voici le résultat : {"subject": "Deal", "actions": []} merci !'
    assert _parse_json(raw) == {"subject": "Deal", "actions": []}


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError):
        _parse_json("ceci n'est pas du JSON")


def test_parse_empty_string_raises():
    with pytest.raises(ValueError):
        _parse_json("")


def test_system_prompt_injects_today():
    rendered = SYSTEM_PROMPT.format(today="2026-06-22")
    assert "2026-06-22" in rendered
    assert "Procès-Verbal" in rendered


def test_user_prompt_injects_transcript():
    rendered = USER_PROMPT.format(transcript="[10:00:00] Ahmed : Bonjour")
    assert "[10:00:00] Ahmed : Bonjour" in rendered
