"""WebSocket call handler — multi-member (per-device) real-time calls.

Each member connects to ``/ws/call/{session_id}/{speaker_id}`` and streams its
own microphone audio (PCM S16LE, 16 kHz, mono) as binary frames. Two things
happen with those frames:

1. **Audio bridge** — they are relayed verbatim to the other members, so callers
   hear each other (the "call" itself).
2. **Agent listening** — while the *session-wide* agent toggle is on (any member
   sends ``{"type":"listen_start"}``), every member's frames are fed to their own
   **independent realtime STT session** (no diarization required). A single
   ``{"type":"listen_stop"}`` from any member ends the whole listening period and
   commits every member's authoritative transcript.

The labeled transcript segments accumulate in the shared session manager and are
interleaved chronologically (see ``app/transcription/merge.py``). When the call
ends — either every member disconnects, or an explicit ``{"type":"end_call"}``
is received — the full AI pipeline runs once on the merged transcript.

Interruption tolerance: each member's STT session is independent, so overlapping
speech is captured by every speaker's own session and interleaved, rather than
being dropped from a single mixed stream.
"""

import asyncio
import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.agent.action_extractor import extract
from app.agent.classifier import classify
from app.agent.summarizer import summarize
from app.config import settings
from app.routing.router import route
from app.transcription import TranscribeError, stream_transcribe
from app.ws.session_manager import MeetingSession, manager

logger = logging.getLogger(__name__)


async def member_handler(
    websocket: WebSocket,
    session_id: str,
    speaker_id: str,
    side: str | None = None,
    role: str | None = None,
    phone: str | None = None,
) -> None:
    """Handle one member's audio stream within a call.

    Two independent concerns share one socket:

    * **Audio bridge** — every binary frame is relayed verbatim to the other
      members, so callers hear each other (the "call" itself).
    * **Agent listening** — while the *session-wide* agent toggle is on, every
      member's frames are also fed to their own realtime STT session. One
      ``listen_start`` from any member turns it on for the whole call; one
      ``listen_stop`` ends the shared listening period and commits transcripts.
    """
    await websocket.accept()
    session = manager.get_or_create(session_id)

    try:
        session.attach(speaker_id, websocket, side=side, role=role, phone=phone)
    except ValueError as exc:
        await websocket.send_json({"type": "error", "session_id": session_id, "message": str(exc)})
        await websocket.close()
        return

    # Announce the updated roster to everyone (including the newcomer).
    await session.broadcast_participants()

    _ensure_incremental(session)

    # Per-member STT task, driven by the SHARED session.agent_listening flag.
    # Each member still runs its own realtime STT session (so overlapping speech
    # stays attributed per speaker), but the on/off toggle is session-wide.
    stt_queue: asyncio.Queue[bytes | None] | None = None
    stt_task: asyncio.Task | None = None
    stt_gen = 0
    stop_requested = False

    async def on_delta(text: str) -> None:
        """Accumulate the live transcript and broadcast captions to everyone."""
        session.add_text(speaker_id, text)
        await session.broadcast({
            "type": "transcript_delta",
            "session_id": session_id,
            "speaker_id": speaker_id,
            "text": text,
        })

    async def _chunks(q: asyncio.Queue):
        while True:
            chunk = await q.get()
            if chunk is None:
                break
            yield chunk

    async def _transcribe_segment(q: asyncio.Queue, gen: int) -> None:
        nonlocal stt_task, stt_queue
        failures = 0
        try:
            # Keep the STT session alive for the whole listening period. A
            # single Mistral connection is fragile — it can drop, or the server
            # can end a segment early (endpointing) — so loop: when one
            # stream_transcribe() call ends, reconnect and keep feeding the same
            # queue until the agent is stopped (listen_stop) or this member
            # disconnects. This is what stops transcription from going dead
            # mid-call.
            while gen == stt_gen:
                try:
                    final_text = await stream_transcribe(_chunks(q), on_delta=on_delta)
                except TranscribeError as exc:
                    failures += 1
                    if gen != stt_gen:
                        break
                    delay = min(settings.stt_reconnect_delay_seconds * (2 ** (failures - 1)), 10.0)
                    logger.warning(
                        "Realtime STT dropped for %s/%s (attempt %d) — reconnecting in %.1fs: %s",
                        session_id, speaker_id, failures, delay, exc,
                    )
                    await asyncio.sleep(delay)
                    continue

                failures = 0
                session.commit_text(speaker_id, final_text)

                if stop_requested or gen != stt_gen:
                    break

                # stream_transcribe() returned on its own (an early
                # transcription.done / endpoint). Reconnect to keep listening.
                logger.info(
                    "Realtime STT segment ended for %s/%s — restarting to keep listening",
                    session_id, speaker_id,
                )
                await asyncio.sleep(settings.stt_reconnect_delay_seconds)
        except Exception:
            logger.exception("Unexpected error in member stream %s/%s", session_id, speaker_id)
        finally:
            if gen == stt_gen:
                stt_task = None
                stt_queue = None

    def _start_listening() -> None:
        nonlocal stt_queue, stt_task, stt_gen, stop_requested
        if stt_task is not None:
            return
        stt_gen += 1
        stop_requested = False
        stt_queue = asyncio.Queue()
        stt_task = asyncio.create_task(_transcribe_segment(stt_queue, stt_gen))

    def _stop_listening() -> None:
        nonlocal stt_queue, stop_requested
        stop_requested = True
        if stt_task is not None and stt_queue is not None:
            stt_queue.put_nowait(None)  # end the current segment

    def _sync_agent_listening() -> None:
        """Align this member's STT task with the session-wide toggle."""
        if session.agent_listening:
            _start_listening()
        else:
            _stop_listening()

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("text") is not None:
                action = await _handle_control(session, msg["text"])
                if action == "end_call":
                    break
                if action in ("listen_start", "listen_stop"):
                    _sync_agent_listening()
                    # Let every member's UI reflect the shared agent state.
                    await session.broadcast({
                        "type": "agent_state",
                        "session_id": session_id,
                        "active": session.agent_listening,
                    })
                continue
            data = msg.get("bytes")
            if data is None:
                continue
            # Always relay so others can hear this member.
            await session.relay_audio(websocket, data)
            # Feed this member's own frames to STT while the session-wide agent
            # is listening (any member can have turned it on).
            _sync_agent_listening()
            if session.agent_listening and stt_queue is not None:
                await stt_queue.put(data)
    except WebSocketDisconnect:
        pass
    finally:
        _stop_listening()
        task = stt_task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=30)
            except (asyncio.TimeoutError, Exception):
                task.cancel()
        session.finish(speaker_id, "")
        # Let the remaining members see that this one left.
        await session.broadcast_participants()
        _maybe_schedule_finalize(session)
        # Keep this socket open so the member receives the broadcast PV.
        await _wait_for_finalize(session)


# ── Control + finalization ──────────────────────────────────────────────


async def _handle_control(session: MeetingSession, raw_text: str) -> str | None:
    """Handle a text (JSON) control frame from a member.

    Returns an action string: ``listen_start``, ``listen_stop``, ``end_call``,
    or ``None`` for unknown frames. ``end_call`` marks the session for
    finalization (the member loop then breaks and triggers it).
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("Ignoring non-JSON control frame in call %s", session.session_id)
        return None

    control_type = payload.get("type")
    if control_type == "listen_start":
        session.agent_listening = True
        logger.info("Agent listening started (session-wide) for call %s", session.session_id)
        return "listen_start"
    if control_type == "listen_stop":
        session.agent_listening = False
        logger.info("Agent listening stopped (session-wide) for call %s", session.session_id)
        return "listen_stop"
    if control_type == "audio_end":
        # Legacy alias — previously signalled end-of-audio; now stops the
        # session-wide agent listening while keeping the audio bridge open.
        session.agent_listening = False
        logger.info("audio_end (legacy) received for call %s", session.session_id)
        return "listen_stop"
    if control_type == "end_call":
        logger.info("end_call received for call %s", session.session_id)
        session.request_end()
        return "end_call"

    return None


def _apply_declared_participants(pv: dict, session: MeetingSession) -> None:
    """Enrich PV participants with what members declared at join.

    The LLM fills ``phone_number`` / ``role`` by guessing (usually empty, since
    a caller's number and job title rarely appear in speech). When a member
    declared them in the lobby, those are ground truth — overwrite the guessed
    values on the matching participant by name.
    """
    details = session.declared_details()
    if not details:
        return
    for key in ("left", "right"):
        participant = pv.get(key)
        if isinstance(participant, dict):
            _merge_declared(participant, details.get(participant.get("name", "")))
    for participant in pv.get("additional_participants", []):
        if isinstance(participant, dict):
            _merge_declared(participant, details.get(participant.get("name", "")))


def _merge_declared(participant: dict, declared: dict | None) -> None:
    """Overwrite phone/role on a single participant with declared values."""
    if not declared:
        return
    if declared.get("phone"):
        participant["phone_number"] = declared["phone"]
    if declared.get("role"):
        participant["role"] = declared["role"]


def _maybe_schedule_finalize(session: MeetingSession) -> None:
    """Kick off finalization when the call is over (idempotent)."""
    if session.finalized or session.delayed_finalize is not None:
        return
    if session.end_requested or session.all_finished():
        asyncio.create_task(_finalize(session))
    elif session.all_disconnected():
        session.delayed_finalize = asyncio.create_task(_finalize_after_grace(session))


async def _finalize_after_grace(session: MeetingSession) -> None:
    """Wait out transient disconnects, then finalize if still all gone."""
    await asyncio.sleep(settings.call_end_grace_seconds)
    session.delayed_finalize = None
    if session.finalized:
        return
    if session.all_disconnected() and session.is_over():
        await _finalize(session)


async def _finalize(session: MeetingSession) -> None:
    """Run the AI pipeline once on the merged transcript and broadcast the PV."""
    if session.finalized:
        return
    session.finalized = True  # set before the first await — no race in asyncio

    try:
        transcript = session.build_transcript()

        if not transcript.strip():
            logger.warning("Empty transcript for call %s — skipping pipeline", session.session_id)
            await _broadcast(session, {
                "type": "error",
                "session_id": session.session_id,
                "message": "No transcript produced — call may have been silent",
            })
            return

        logger.info("Call %s finalizing — %d chars transcript", session.session_id, len(transcript))

        try:
            # Reuse the last incremental draft when the transcript is unchanged —
            # the summarizer already ran during the call, so we skip straight to
            # routing (this is what makes the PV feel "already done" at call end).
            if session.last_draft_pv is not None and len(transcript) == session.last_draft_chars:
                pv = session.last_draft_pv  # already has call_type + actions
            else:
                pv = await summarize(transcript)
                pv["call_type"] = classify(pv.get("call_type"))
                pv["actions"] = extract(pv)

            # Overwrite the LLM's guessed phone/role with what members declared.
            _apply_declared_participants(pv, session)

            routing_result = await route(pv)

            await _broadcast(session, {
                "type": "pv_result",
                "session_id": session.session_id,
                "pv": pv,
                "routing": routing_result,
            })
        except Exception as exc:
            logger.exception("Pipeline failed for call %s", session.session_id)
            await _broadcast(session, {
                "type": "error",
                "session_id": session.session_id,
                "message": f"Pipeline error: {exc}",
            })
    finally:
        session.finalized_event.set()
        manager.remove(session.session_id)


def _ensure_incremental(session: MeetingSession) -> None:
    """Start the background incremental pipeline once per call."""
    if session.draft_task is not None or session.finalized:
        return
    session.draft_task = asyncio.create_task(_incremental_loop(session))


async def _incremental_loop(session: MeetingSession) -> None:
    """Periodically summarize the transcript-so-far and broadcast a draft PV.

    Runs only summarize → classify → extract (NOT route) — routing has side
    effects (HubSpot / fallback store) and must wait for finalization. The
    draft PV is broadcast as ``pv_draft`` so the UI can show live progress.
    """
    while not session.finalized:
        await asyncio.sleep(settings.pipeline_interval_seconds)
        if session.finalized:
            break

        transcript = session.build_transcript()
        if len(transcript) < settings.pipeline_min_chars:
            continue
        if len(transcript) <= session.last_draft_chars:
            continue

        session.last_draft_chars = len(transcript)
        try:
            draft = await summarize(transcript)
            draft["call_type"] = classify(draft.get("call_type"))
            draft["actions"] = extract(draft)
            _apply_declared_participants(draft, session)
            session.last_draft_pv = draft
            await _broadcast(session, {
                "type": "pv_draft",
                "session_id": session.session_id,
                "pv": draft,
            })
        except Exception as exc:
            logger.warning("Incremental draft failed for call %s: %s", session.session_id, exc)


async def _wait_for_finalize(session: MeetingSession) -> None:
    """Keep a member's socket open until the call finalizes (PV is broadcast)."""
    try:
        await asyncio.wait_for(session.finalized_event.wait(), timeout=120)
    except asyncio.TimeoutError:
        logger.warning("Timed out waiting for call %s to finalize", session.session_id)


async def _broadcast(session: MeetingSession, payload: dict) -> None:
    """Send a JSON payload to every still-connected member."""
    await session.broadcast(payload)
