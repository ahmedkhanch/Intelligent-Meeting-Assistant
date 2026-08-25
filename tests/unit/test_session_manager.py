"""Tests for the multi-member session manager (app/ws/session_manager.py)."""

import pytest

from app.ws.session_manager import MeetingSession, SessionManager


def test_manager_get_or_create_is_singleton_per_session():
    mgr = SessionManager()
    a = mgr.get_or_create("s1")
    b = mgr.get_or_create("s1")
    c = mgr.get_or_create("s2")
    assert a is b
    assert a is not c
    assert mgr.get("missing") is None


def test_attach_detach_finish_lifecycle():
    session = MeetingSession(session_id="s1")
    session.attach("Sami", ws="ws-sami")
    assert session.members["Sami"].connected

    session.detach("Sami")
    assert not session.members["Sami"].connected
    assert session.all_disconnected()

    session.attach("Sami", ws="ws-sami")
    session.finish("Sami", "Bonjour")
    assert session.members["Sami"].finished
    assert not session.members["Sami"].connected


def test_add_text_accumulates_live_transcript():
    session = MeetingSession(session_id="s1")
    session.add_text("Sami", "Bonjour ")
    session.add_text("Sami", "tout le monde")
    assert session.build_transcript().startswith("[00:00:00] Sami : Bonjour tout le monde")


def test_finish_replaces_deltas_with_authoritative_final_text():
    session = MeetingSession(session_id="s1")
    session.add_text("Sami", "Bonjour (révision intermédiaire) ")
    session.finish("Sami", "Bonjour tout le monde")
    out = session.build_transcript()
    assert "Bonjour tout le monde" in out
    assert "révision intermédiaire" not in out


def test_finish_sets_final_text_when_no_deltas():
    session = MeetingSession(session_id="s1")
    session.attach("kh", ws=None)
    session.finish("kh", "Le résumé complet")
    assert "kh : Le résumé complet" in session.build_transcript()


def test_add_text_ignores_blank():
    session = MeetingSession(session_id="s1")
    session.add_text("Sami", "   ")
    assert session.build_transcript() == ""


def test_is_over_and_end_request():
    session = MeetingSession(session_id="s1")
    session.attach("Sami", ws=None)
    assert not session.is_over()

    session.request_end()
    assert session.is_over()

    session2 = MeetingSession(session_id="s2")
    session2.attach("a", ws=None)
    session2.attach("b", ws=None)
    session2.finish("a", "")
    assert not session2.is_over()          # b not finished yet
    session2.finish("b", "")
    assert session2.is_over()              # all finished


def test_max_members_cap():
    session = MeetingSession(session_id="s1")
    from app.config import settings
    for i in range(settings.max_members_per_call):
        session.attach(f"m{i}", ws=None)
    with pytest.raises(ValueError):
        session.attach("overflow", ws=None)


def test_build_transcript_labels_all_members():
    session = MeetingSession(session_id="s1")
    session.add_text("kh", "Premier point")
    session.add_text("Lina", "Deuxième point")
    session.add_text("Sami", "Troisième point")
    out = session.build_transcript()
    assert "kh : Premier point" in out
    assert "Lina : Deuxième point" in out
    assert "Sami : Troisième point" in out


def test_build_transcript_prepends_participant_manifest():
    session = MeetingSession(session_id="s1")
    session.attach("kh", ws=None, side="left", role="CTO")
    session.attach("Lina", ws=None, side="right")
    session.add_text("kh", "Bonjour")
    session.add_text("Lina", "Bonjour kh")
    out = session.build_transcript()
    assert out.startswith("PARTICIPANTS: kh (côté Ora Telecom, CTO) ; Lina (externe)")
    assert "kh : Bonjour" in out


def test_no_manifest_without_declared_side():
    session = MeetingSession(session_id="s1")
    session.attach("kh", ws=None)
    session.add_text("kh", "Bonjour")
    assert session.build_transcript().startswith("[00:00:00] kh : Bonjour")


def test_live_websockets_excludes_detached():
    session = MeetingSession(session_id="s1")
    session.attach("a", ws="ws-a")
    session.attach("b", ws="ws-b")
    session.detach("a")
    assert session.live_websockets() == ["ws-b"]


def test_attach_cancels_pending_delayed_finalize():
    class _FakeTask:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    session = MeetingSession(session_id="s1")
    fake_task = _FakeTask()
    session.delayed_finalize = fake_task

    session.attach("a", ws=None)
    assert session.delayed_finalize is None
    assert fake_task.cancelled is True
