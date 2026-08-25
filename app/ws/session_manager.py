"""Multi-member call session manager.

Each member of a WebRTC meeting connects over its own WebSocket and streams its
own audio into its own realtime STT session. This module tracks those members
per call (``session_id``) and accumulates their live transcript so that:

- a draft PV can be generated **while the call is still running**, and
- a single labeled transcript is available at finalization.

The manager is pure state + helpers — it does NOT run the pipeline itself.
The call handler orchestrates: it feeds text here and triggers finalization.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.transcription.merge import Segment, interleave_segments

logger = logging.getLogger(__name__)


@dataclass
class _Member:
    """State for a single member's stream within a call."""

    connected: bool = False
    finished: bool = False
    text: str = ""                  # authoritative transcript (committed segments)
    live_text: str = ""             # interim deltas for the currently-active segment
    first_ts: float | None = None   # seconds since call start at first speech
    ws: Any | None = None           # live WebSocket, for broadcasting results + audio
    side: str | None = None         # declared side: "left" (Ora) or "right" (external)
    role: str | None = None         # declared role (job title / occupation), if any
    phone: str | None = None        # declared phone number, if any
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


@dataclass
class MeetingSession:
    """All live state for one call (one ``session_id``)."""

    session_id: str
    start_monotonic: float = field(default_factory=time.monotonic)
    members: dict[str, _Member] = field(default_factory=dict)
    end_requested: bool = False
    agent_listening: bool = False      # session-wide "agent is listening" toggle
    finalized: bool = False
    finalized_event: asyncio.Event = field(default_factory=asyncio.Event)
    delayed_finalize: Any | None = None  # asyncio.Task scheduled on last-disconnect
    draft_task: Any | None = None        # incremental pipeline task (started once)
    last_draft_chars: int = 0            # transcript length at the last draft run
    last_draft_pv: dict | None = None    # cached PV from the last draft run

    # ── Membership ─────────────────────────────────────────────────────

    def attach(
        self,
        speaker_id: str,
        ws: Any,
        side: str | None = None,
        role: str | None = None,
        phone: str | None = None,
    ) -> None:
        """Register (or re-register) a member and mark it connected.

        ``side`` / ``role`` / ``phone`` are optional declarations from the
        client (e.g. the WebRTC page knows who is Ora vs external, and the
        lobby already collected each caller's job title + phone number). ``side``
        feeds a participant manifest that removes the LLM's side-guessing
        ambiguity; ``role`` / ``phone`` enrich the PV deterministically.
        """
        if len(self.members) >= settings.max_members_per_call and speaker_id not in self.members:
            raise ValueError(
                f"Call {self.session_id} already has {settings.max_members_per_call} members"
            )
        if self.delayed_finalize is not None:
            # A member (re)joined during the end-of-call grace period — abort it.
            self.delayed_finalize.cancel()
            self.delayed_finalize = None
        member = self.members.setdefault(speaker_id, _Member())
        member.connected = True
        member.ws = ws
        if side:
            member.side = side
        if role:
            member.role = role
        if phone:
            member.phone = phone
        logger.info("Member %s attached to call %s", speaker_id, self.session_id)

    def detach(self, speaker_id: str) -> None:
        """Mark a member disconnected (transient — may reconnect)."""
        member = self.members.get(speaker_id)
        if member:
            member.connected = False
            member.ws = None

    def add_text(self, speaker_id: str, text: str) -> None:
        """Accumulate live interim deltas (captions + draft), not final text."""
        if not text:
            return
        member = self.members.setdefault(speaker_id, _Member())
        member.live_text += text
        if member.first_ts is None:
            member.first_ts = time.monotonic() - self.start_monotonic

    def commit_text(self, speaker_id: str, final_text: str) -> None:
        """Commit one authoritative transcription segment to the transcript.

        Called when a listening segment finishes (``transcription.done``). The
        authoritative text replaces that segment's interim deltas, which are
        cleared. On an empty authoritative result the interim deltas are kept as
        the best available fallback.
        """
        member = self.members.setdefault(speaker_id, _Member())
        if final_text and final_text.strip():
            member.text += final_text
            member.live_text = ""

    def finish(self, speaker_id: str, final_text: str) -> None:
        """Mark a member's stream complete.

        ``final_text`` (if any) is the authoritative text of a still-active
        segment; it is committed the same way as ``commit_text``. The member is
        then marked finished and disconnected.
        """
        member = self.members.setdefault(speaker_id, _Member())
        member.finished = True
        member.connected = False
        # NOTE: keep member.ws so a pending finalize can still broadcast the PV
        # to this socket (it is closed by the time the session is removed).
        if final_text and final_text.strip():
            member.text += final_text
            member.live_text = ""

    def request_end(self) -> None:
        """An explicit ``end_call`` control message was received."""
        self.end_requested = True

    # ── Queries ────────────────────────────────────────────────────────

    def all_disconnected(self) -> bool:
        """True if every member has disconnected (or no members yet)."""
        return bool(self.members) and all(not m.connected for m in self.members.values())

    def all_finished(self) -> bool:
        """True if every member has signaled end-of-audio (finished)."""
        return bool(self.members) and all(m.finished for m in self.members.values())

    def is_over(self) -> bool:
        """True when the call should be finalized (explicit end, or all done)."""
        return self.end_requested or self.all_finished()

    def build_transcript(self) -> str:
        """Build the current labeled transcript from every member's text.

        Members are ordered by their first-speech time (falling back to 0),
        producing the ``INPUT_SCHEMA.md`` format ``[HH:MM:SS] Speaker : text``.
        When any member declared a ``side``, a participant manifest line is
        prepended so the summarizer can assign left/right deterministically.
        """
        segments = [
            Segment(
                ts=m.first_ts if m.first_ts is not None else 0.0,
                speaker=speaker_id,
                text=m.text + m.live_text,
            )
            for speaker_id, m in self.members.items()
            if (m.text + m.live_text).strip()
        ]
        body = interleave_segments(segments)
        manifest = self._participant_manifest()
        return f"{manifest}\n\n{body}" if manifest else body

    def _participant_manifest(self) -> str:
        """Return a ``PARTICIPANTS:`` header for members that declared a side."""
        entries = []
        for speaker_id, m in self.members.items():
            if m.side not in ("left", "right"):
                continue
            label = "côté Ora Telecom" if m.side == "left" else "externe"
            if m.role:
                label += f", {m.role}"
            entries.append(f"{speaker_id} ({label})")
        if not entries:
            return ""
        return "PARTICIPANTS: " + " ; ".join(entries)

    def live_websockets(self) -> list[Any]:
        """WebSockets to broadcast results to (any member with an open socket)."""
        return [m.ws for m in self.members.values() if m.ws is not None]

    async def relay_audio(self, sender_ws: Any, data: bytes) -> None:
        """Relay one member's audio frame to every other connected member.

        This is what lets callers hear each other: each member's mic PCM is
        forwarded verbatim (16 kHz mono S16LE) to the other members, who play it
        back locally. The ``send_lock`` serialises the concurrent fan-in so
        frames from multiple relayers never interleave on one socket.
        """
        for m in self.members.values():
            if m.ws is None or m.ws is sender_ws:
                continue
            async with m.send_lock:
                try:
                    await m.ws.send_bytes(data)
                except Exception:
                    logger.debug("Relay to a member of call %s failed", self.session_id, exc_info=True)

    async def broadcast(self, payload: dict) -> None:
        """Send a JSON payload to every member with an open socket."""
        for m in self.members.values():
            if m.ws is None:
                continue
            async with m.send_lock:
                try:
                    await m.ws.send_json(payload)
                except Exception:
                    logger.debug("Broadcast to a member of call %s failed", self.session_id, exc_info=True)

    def connected_members(self) -> list[dict[str, Any]]:
        """Snapshot of the members currently in the call (for the roster UI)."""
        return [
            {
                "speaker_id": speaker_id,
                "side": m.side,
                "role": m.role,
            }
            for speaker_id, m in self.members.items()
            if m.connected
        ]

    def declared_details(self) -> dict[str, dict[str, str]]:
        """Speaker identity details members declared at join (phone + role).

        The LLM cannot reliably learn a caller's phone number or job title from
        audio alone, but the lobby collects them up front. Return them keyed by
        speaker name so the PV can be enriched deterministically after
        summarization instead of relying on the LLM to guess.
        """
        out: dict[str, dict[str, str]] = {}
        for speaker_id, m in self.members.items():
            phone = (m.phone or "").strip()
            role = (m.role or "").strip()
            if phone or role:
                out[speaker_id] = {"phone": phone, "role": role, "side": m.side or ""}
        return out

    async def broadcast_participants(self) -> None:
        """Broadcast the current roster to every connected member."""
        await self.broadcast({
            "type": "participants",
            "session_id": self.session_id,
            "members": self.connected_members(),
        })


class SessionManager:
    """In-memory registry of active calls, keyed by ``session_id``."""

    def __init__(self) -> None:
        self._sessions: dict[str, MeetingSession] = {}

    def get_or_create(self, session_id: str) -> MeetingSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = MeetingSession(session_id=session_id)
        return self._sessions[session_id]

    def get(self, session_id: str) -> MeetingSession | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# Module-level singleton — the call handler imports this.
manager = SessionManager()
