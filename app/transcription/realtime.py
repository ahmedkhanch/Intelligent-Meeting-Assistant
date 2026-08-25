"""Realtime WebSocket client for Mistral VoxTral streaming transcription.

Connects to wss://api.mistral.ai/v1/audio/transcriptions/realtime, sends audio
chunks as they arrive, and returns the full transcript when the stream ends.

Mistral event contract (see the `mistralai` SDK `RealtimeEvent` union):
    session.created          → handshake acknowledgement
    session.updated          → ack for our session.update
    transcription.text.delta → incremental/interim text  (streamed live)
    transcription.segment    → completed segment (has timestamps; NOT used for
                               accumulation — would double-count vs. deltas)
    transcription.language   → detected audio language
    transcription.done       → authoritative final transcript (event.text)
    error                    → server error

The function returns the authoritative transcript from ``transcription.done``,
falling back to the concatenation of ``text.delta`` fragments if ``done`` is
never received (e.g. near-silent audio).
"""

import asyncio
import base64
import json
import logging
from typing import AsyncIterator, Awaitable, Callable

from websockets import connect

from app.config import settings
from app.transcription.errors import TranscribeError

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────

_WS_PATH = "/v1/audio/transcriptions/realtime"

# ── Public API ──────────────────────────────────────────────────────────


async def stream_transcribe(
    audio_chunks: AsyncIterator[bytes],
    *,
    sample_rate: int = 16000,
    encoding: str = "pcm_s16le",
    language: str | None = None,
    diarize: bool = False,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
    on_segment: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Stream audio chunks to Mistral and return the full transcript.

    Args:
        audio_chunks: Async iterator yielding raw PCM audio bytes (16 kHz,
            S16LE, mono).
        sample_rate: Audio sample rate in Hz (default 16000).
        encoding: Audio encoding format (default pcm_s16le).
        language: ISO language code (e.g. "fr", "en"). Auto-detected if None.
        diarize: Whether to identify speakers. NOT supported by the realtime
            API — a warning is logged and it is ignored.
        on_delta: Optional async callback invoked with each live text delta
            (for real-time captions). Receives incremental fragments.
        on_segment: Optional async callback invoked with each completed
            transcription segment (a full utterance, as opposed to partial
            deltas). Useful for building a clean per-speaker transcript in
            multi-track (per-member) setups. The single-stream path ignores
            segments to avoid double-counting against the deltas.

    Returns:
        The full transcript text (authoritative, from ``transcription.done``).

    Raises:
        TranscribeError: On connection failure or server error.
    """
    ws_url = _build_url()

    if diarize:
        logger.warning(
            "Diarization is not supported by the realtime API — ignoring --diarize"
        )

    logger.info("Connecting to Mistral realtime STT: %s", ws_url)

    try:
        async with connect(
            ws_url,
            additional_headers={"Authorization": f"Bearer {settings.voxtral_api_key}"},
            open_timeout=15,
            # Disable the websockets library's keepalive pings (default every
            # 20s). Mistral's realtime endpoint doesn't reliably answer protocol
            # pings, and an unanswered ping makes *our own client* tear down an
            # otherwise-healthy transcription stream at ~40s — the classic
            # "it transcribed a bit, then stopped" failure. The call handler
            # reconnects on genuine drops instead.
            ping_interval=None,
        ) as ws:
            # ── Handshake: wait for session.created ──────────────────
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            event = json.loads(raw)
            if event.get("type") == "error":
                raise TranscribeError(event.get("error", {}).get("message", raw))
            logger.debug("Session created: %s", event.get("session", {}).get("id", "?"))

            # ── Configure session ────────────────────────────────────
            # The model is already in the URL query string. The realtime
            # session config only accepts `audio_format` (language is
            # auto-detected; `model`/`language` are rejected as extra fields).
            session_data: dict = {
                "audio_format": {
                    "encoding": encoding,
                    "sample_rate": sample_rate,
                },
            }
            if language:
                logger.info("Language hint '%s' ignored — realtime auto-detects language", language)
            await ws.send(json.dumps({
                "type": "session.update",
                "session": session_data,
            }))

            # ── Background reader ────────────────────────────────────
            # Reading the socket directly in the send loop would block on
            # recv() and stall the audio feed. A dedicated reader task
            # queues events so the main loop can keep sending at real-time
            # pace.
            queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
            done_text: str | None = None
            accumulated_parts: list[str] = []

            async def reader() -> None:
                nonlocal done_text
                try:
                    async for raw in ws:
                        kind, text = _parse_event(raw)
                        if kind == "delta":
                            await queue.put(("delta", text))
                        elif kind == "segment":
                            if on_segment:
                                await on_segment(text)
                        elif kind == "done":
                            done_text = text
                            await queue.put(("done", text))
                            return
                except Exception:
                    # Only reached on a real error (ConnectionClosed, etc.) —
                    # CancelledError inherits from BaseException and is not
                    # caught here. Log loudly so a dropped Mistral connection
                    # is visible instead of silently killing transcription.
                    logger.warning("Realtime reader ended unexpectedly", exc_info=True)

            reader_task = asyncio.create_task(reader())

            try:
                # ── Send audio chunks at the caller's pace ───────────
                async for chunk in audio_chunks:
                    await ws.send(json.dumps({
                        "type": "input_audio.append",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                    }))

                    # Drain any deltas that arrived since the last chunk.
                    got_done = False
                    while True:
                        try:
                            kind, text = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if kind == "delta":
                            accumulated_parts.append(text)
                            if on_delta:
                                await on_delta(text)
                        elif kind == "done":
                            got_done = True
                            break
                    if got_done:
                        break

                # ── Signal end of audio ──────────────────────────────
                await ws.send(json.dumps({"type": "input_audio.end"}))

                # ── Collect the final transcript ─────────────────────
                while True:
                    # Stop early if the server closed and we've drained it.
                    if reader_task.done() and queue.empty():
                        break
                    try:
                        kind, text = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        logger.warning("No transcription.done received before timeout")
                        break
                    if kind == "delta":
                        accumulated_parts.append(text)
                        if on_delta:
                            await on_delta(text)
                    elif kind == "done":
                        done_text = text
                        break

            finally:
                reader_task.cancel()
                try:
                    await reader_task
                except (asyncio.CancelledError, Exception):
                    pass

            if done_text:
                return done_text
            # Fallback: reconstruct from the deltas we did receive.
            return "".join(accumulated_parts)

    except TranscribeError:
        raise
    except Exception as exc:
        raise TranscribeError(f"Realtime STT connection failed: {exc}") from exc

    logger.info("Realtime transcription stream ended")


# ── Helpers ─────────────────────────────────────────────────────────────


def _build_url() -> str:
    """Convert the REST base URL to a WebSocket URL carrying the model.

    The Mistral managed realtime API expects:
      wss://api.mistral.ai/v1/audio/transcriptions/realtime?model=...

    Auth is sent via the ``Authorization: Bearer`` header (not the URL), so the
    key never appears in logs.
    """
    base = settings.voxtral_base_url
    # https://api.mistral.ai → wss://api.mistral.ai
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    params = f"model={settings.voxtral_realtime_model}"
    return f"{ws_base}{_WS_PATH}?{params}"


def _parse_event(raw: str | bytes) -> tuple[str | None, str]:
    """Parse a single WebSocket event.

    Returns:
        A (kind, text) tuple. ``kind`` is "delta" (incremental text),
        "segment" (completed utterance), "done" (authoritative final
        transcript), or None (ignored).
    """
    try:
        event = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
    except json.JSONDecodeError:
        return (None, "")

    event_type = event.get("type", "")

    if event_type == "transcription.text.delta":
        return ("delta", event.get("text", ""))
    if event_type == "transcription.done":
        return ("done", event.get("text", ""))
    if event_type == "transcription.segment":
        # Completed-segment event — a full utterance. The single-stream path
        # ignores it to avoid double-counting vs. deltas, but multi-track
        # callers use it (via on_segment) to build a clean labeled transcript.
        return ("segment", event.get("text", ""))
    if event_type == "transcription.language":
        logger.debug("Detected audio language: %s", event.get("audio_language"))
        return (None, "")
    if event_type == "error":
        msg = event.get("error", {}).get("message", str(event))
        logger.error("Mistral realtime error: %s", msg)
        return (None, "")

    logger.debug("Unhandled event type: %s", event_type)
    return (None, "")
