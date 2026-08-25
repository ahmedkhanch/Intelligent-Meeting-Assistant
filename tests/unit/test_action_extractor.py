"""Tests for the action extractor — validation & enrichment of call actions."""

import pytest

from app.agent.action_extractor import extract


def test_commercial_actions_have_no_difficulty_or_hint():
    pv = {
        "call_type": "#appel-commercial",
        "actions": [
            {"title": "Envoyer la proposition", "owner": "Ahmed", "deadline": "2026-06-20"},
        ],
    }
    out = extract(pv)
    assert len(out) == 1
    action = out[0]
    assert action["title"] == "Envoyer la proposition"
    assert action["owner"] == "Ahmed"
    assert action["deadline"] == "2026-06-20"
    assert action["difficulty"] is None
    assert action["model_hint"] is None


@pytest.mark.parametrize(
    ("difficulty", "expected_hint"),
    [
        ("facile", "gpt-4o-mini"),
        ("difficile", "claude-sonnet-4-6"),
        ("très difficile", "claude-opus-4-6"),
    ],
)
def test_tech_difficulty_maps_to_model_hint(difficulty, expected_hint):
    pv = {
        "call_type": "#appel-tech",
        "actions": [{"title": "Tâche", "owner": "Oussema", "difficulty": difficulty}],
    }
    action = extract(pv)[0]
    assert action["difficulty"] == difficulty
    assert action["model_hint"] == expected_hint


def test_tech_missing_difficulty_defaults_to_difficile():
    pv = {
        "call_type": "#appel-tech",
        "actions": [{"title": "Tâche", "owner": "Oussema"}],
    }
    action = extract(pv)[0]
    assert action["difficulty"] == "difficile"
    assert action["model_hint"] == "claude-sonnet-4-6"


def test_skips_action_without_title():
    pv = {"call_type": "#appel-commercial", "actions": [{"owner": "Ahmed"}]}
    assert extract(pv) == []


def test_skips_action_without_owner():
    pv = {"call_type": "#appel-commercial", "actions": [{"title": "Sans owner"}]}
    assert extract(pv) == []


def test_skips_blank_title_and_owner():
    pv = {
        "call_type": "#appel-commercial",
        "actions": [{"title": "   ", "owner": "   "}],
    }
    assert extract(pv) == []


def test_invalid_deadline_becomes_none():
    pv = {
        "call_type": "#appel-commercial",
        "actions": [{"title": "T", "owner": "O", "deadline": "not-a-date"}],
    }
    action = extract(pv)[0]
    assert action["deadline"] is None


def test_strips_title_and_owner_whitespace():
    pv = {
        "call_type": "#appel-commercial",
        "actions": [{"title": "  Tâche  ", "owner": "  Ahmed  "}],
    }
    action = extract(pv)[0]
    assert action["title"] == "Tâche"
    assert action["owner"] == "Ahmed"


def test_extract_logs_valid_count_across_mixed_actions():
    pv = {
        "call_type": "#appel-commercial",
        "actions": [
            {"title": "Valide", "owner": "Ahmed"},
            {"title": "Sans owner"},
        ],
    }
    out = extract(pv)
    assert len(out) == 1
    assert out[0]["title"] == "Valide"
