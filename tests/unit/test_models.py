"""Tests for the Pydantic schemas — PV, Participant, TaskItem, CallSession."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.models.call import CallSession, CallStartRequest
from app.models.pv import PV, Participant
from app.models.task import TaskItem


def _participant(side: str = "left") -> Participant:
    return Participant(name="Ahmed", phone_number="+216", role="AM", side=side)


def test_taskitem_resolve_model_facile():
    assert TaskItem(title="t", owner="o", difficulty="facile").resolve_model == "gpt-4o-mini"


def test_taskitem_resolve_model_difficile():
    assert (
        TaskItem(title="t", owner="o", difficulty="difficile").resolve_model
        == "claude-sonnet-4-6"
    )


def test_taskitem_resolve_model_tres_difficile():
    assert (
        TaskItem(title="t", owner="o", difficulty="très difficile").resolve_model
        == "claude-opus-4-6"
    )


def test_taskitem_resolve_model_defaults_without_difficulty():
    assert TaskItem(title="t", owner="o").resolve_model == "claude-sonnet-4-6"


def test_taskitem_deadline_is_optional():
    task = TaskItem(title="t", owner="o")
    assert task.deadline is None
    assert task.difficulty is None


def test_taskitem_serializes_deadline_to_iso():
    task = TaskItem(title="t", owner="o", deadline=date(2026, 6, 20))
    assert task.model_dump(mode="json")["deadline"] == "2026-06-20"


def test_participant_rejects_invalid_side():
    with pytest.raises(ValidationError):
        Participant(name="x", phone_number="p", role="r", side="middle")


def test_pv_requires_call_date():
    with pytest.raises(ValidationError):
        PV(  # missing call_date
            call_type="#appel-tech",
            left=_participant(),
            right=_participant("right"),
            subject="s",
            compte_rendu="résumé",
        )


def test_pv_requires_compte_rendu():
    with pytest.raises(ValidationError):
        PV(  # missing compte_rendu
            call_date=datetime(2026, 6, 22),
            call_type="#appel-tech",
            left=_participant(),
            right=_participant("right"),
            subject="s",
        )


def test_pv_builds_with_required_fields():
    pv = PV(
        call_date=datetime(2026, 6, 22),
        call_type="#appel-tech",
        left=_participant(),
        right=_participant("right"),
        subject="Infra",
        compte_rendu="résumé",
    )
    assert pv.call_type == "#appel-tech"
    assert pv.actions == []  # default_factory
    assert pv.meeting_created is False


def test_pv_generates_id_by_default():
    pv = PV(
        call_date=datetime(2026, 6, 22),
        call_type="#appel-commercial",
        left=_participant(),
        right=_participant("right"),
        subject="s",
        compte_rendu="résumé",
    )
    assert pv.pv_id  # non-empty uuid


def test_call_session_default_state_is_waiting():
    session = CallSession(session_id="s1")
    assert session.state == "waiting"
    assert session.pv is None
    assert session.transcript == ""


def test_call_start_request_generates_session_id():
    req = CallStartRequest(
        left=_participant(),
        right=_participant("right"),
        subject="s",
    )
    assert req.session_id
