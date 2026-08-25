#!/usr/bin/env python
"""Live replay simulator — stream a meeting audio file in real-time.

Feeds a .wav file into the *realtime* STT path (stream_transcribe), pacing the
chunks at real-time speed so the call takes as long as the audio actually is —
the opposite of the batch path (scripts/e2e_test.py --audio), which uploads the
whole file at once.

Once the stream ends, it runs the full AI pipeline (summarize → classify →
extract → route), exactly like app/ws/call_handler.py will for live calls.

Usage:
  # Full meeting at real-time speed (4-min audio ≈ 4 min)
  python scripts/live_replay.py --audio final_test_sample.wav

  # Faster for testing (2× speed → 4-min audio ≈ 2 min)
  python scripts/live_replay.py --audio final_test_sample.wav --speed 2

  # Only stream the first 30 seconds, then run the pipeline
  python scripts/live_replay.py --audio tech_meeting_test.wav --max-seconds 30

  # Transcribe only (skip the AI pipeline) — good for isolating STT
  python scripts/live_replay.py --audio tech_meeting_test.wav --no-pipeline

Requirements:
  - VOXTRAL_API_KEY   → Mistral realtime STT
  - DEEPSEEK_API_KEY  → LLM summarization (unless --no-pipeline)
  - The .wav must be PCM S16LE, 16 kHz, mono (scripts/generate_meeting_audio.py
    produces exactly this via its --format wav conversion).
"""

import argparse
import asyncio
import io
import json
import logging
import sys
import wave
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.transcription import stream_transcribe, TranscribeError
from app.agent.summarizer import summarize
from app.agent.classifier import classify
from app.agent.action_extractor import extract
from app.routing.router import route
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_replay")

# ── CLI ──────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRM Vocal — Live Replay (real-time audio → STT → pipeline)",
    )
    parser.add_argument(
        "--audio", "-a",
        type=Path,
        required=True,
        help="Path to a .wav file (PCM S16LE, 16 kHz, mono).",
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="fr",
        help="Language hint for STT (default: fr).",
    )
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=100,
        help="Audio chunk size in milliseconds (default: 100).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier. 1.0 = real-time (default). 2.0 = 2× faster.",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=0.0,
        help="Only stream the first N seconds of audio (0 = whole file).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().isoformat(),
        help="Call date in ISO format (default: now).",
    )
    parser.add_argument(
        "--no-pipeline",
        action="store_true",
        help="Transcribe only — skip summarizer/classifier/extractor/router.",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output only the final PV as JSON (implies pipeline).",
    )
    parser.add_argument(
        "--save-transcript",
        type=Path,
        default=None,
        help="Save the transcribed text to a file.",
    )
    return parser.parse_args()


# ── Audio reading ────────────────────────────────────────────────────────


def open_wav(path: Path) -> tuple[wave.Wave_read, int, int]:
    """Open a WAV and return (handle, sample_rate, frames_per_chunk)."""
    wf = wave.open(str(path), "rb")
    if wf.getcomptype() != "NONE":
        raise ValueError(f"{path.name} is compressed ({wf.getcomptype()}) — must be raw PCM")

    rate = wf.getframerate()
    channels = wf.getnchannels()
    sampwidth = wf.getsampwidth()

    if not (rate == 16000 and channels == 1 and sampwidth == 2):
        logger.warning(
            "Audio is %d Hz / %d ch / %d-byte — VoxTral expects 16000 Hz / 1 ch / 2-byte (PCM S16LE). "
            "Transcription may fail; re-encode with ffmpeg: -ar 16000 -ac 1 -sample_fmt s16",
            rate, channels, sampwidth,
        )

    return wf, rate, channels * sampwidth


def iter_frames(wf: wave.Wave_read, bytes_per_frame: int, chunk_ms: int, speed: float, max_seconds: float):
    """Synchronous generator yielding real-time-paced audio chunks.

    Pacing happens in the async layer (see stream_frames) — this just slices
    the raw frame data into chunk-sized byte strings.
    """
    frames_per_chunk = max(1, int(wf.getframerate() * chunk_ms / 1000))
    bytes_per_chunk = frames_per_chunk * bytes_per_frame

    max_frames = None
    if max_seconds and max_seconds > 0:
        max_frames = int(wf.getframerate() * max_seconds)

    frames_read = 0
    while True:
        if max_frames is not None and frames_read >= max_frames:
            break
        n = frames_per_chunk
        if max_frames is not None:
            n = min(n, max_frames - frames_read)
        data = wf.readframes(n)
        if not data:
            break
        frames_read += n
        yield data


async def stream_frames(wf: wave.Wave_read, bytes_per_frame: int, chunk_ms: int, speed: float, max_seconds: float):
    """Async generator: yield audio chunks paced at real-time speed."""
    sleep_s = (chunk_ms / 1000.0) / speed
    for data in iter_frames(wf, bytes_per_frame, chunk_ms, speed, max_seconds):
        yield data
        await asyncio.sleep(sleep_s)


# ── Pipeline ─────────────────────────────────────────────────────────────


async def run_pipeline(transcript: str, call_date: str) -> dict:
    """Summarize → classify → extract → route (mirrors call_handler)."""
    print("\n" + "─" * 70)
    print("  Pipeline: SUMMARIZER → CLASSIFIER → EXTRACTOR → ROUTER")
    print("─" * 70)

    pv = await summarize(transcript, call_date=call_date)
    print(f"  ✅ PV generated (pv_id: {pv.get('pv_id', 'N/A')})")
    print(f"     Call type (AI):   {pv.get('call_type', 'N/A')}")
    print(f"     Subject:          {pv.get('subject', 'N/A')}")

    pv["call_type"] = classify(pv.get("call_type"))
    pv["actions"] = extract(pv)

    result = await route(pv)
    print(f"  ✅ Routing: {json.dumps(result, ensure_ascii=False)}")

    return pv


# ── Main ─────────────────────────────────────────────────────────────────


async def main() -> None:
    args = parse_args()

    if not args.audio.exists():
        print(f"❌ Audio file not found: {args.audio}")
        sys.exit(1)

    if args.speed <= 0:
        print("❌ --speed must be > 0")
        sys.exit(1)

    if not settings.voxtral_api_key:
        print("❌ VOXTRAL_API_KEY is not set in .env — cannot transcribe audio.")
        print("   Get a key at: https://console.mistral.ai/api-keys")
        sys.exit(1)

    wf, rate, bytes_per_frame = open_wav(args.audio)
    total_frames = wf.getnframes()
    total_seconds = total_frames / rate
    stream_seconds = min(total_seconds, args.max_seconds) if args.max_seconds else total_seconds

    print("=" * 70)
    print("  LIVE REPLAY — real-time audio → STT → pipeline")
    print("=" * 70)
    print(f"  🎤 Audio file : {args.audio.name}")
    print(f"  ⏱  Duration    : {total_seconds:.1f}s  (streaming {stream_seconds:.1f}s)")
    print(f"  📦 Chunk size  : {args.chunk_ms} ms")
    print(f"  ⚡ Speed       : {args.speed}×  (~{stream_seconds / args.speed:.0f}s wall time)")
    print(f"  🌐 STT model   : {settings.voxtral_realtime_model}  (realtime)")
    print(f"  🧠 Pipeline    : {'off (--no-pipeline)' if args.no_pipeline else 'summarize → classify → extract → route'}")
    print()

    # ── Live captions callback ─────────────────────────────────────
    caption_started = False

    async def on_delta(delta: str) -> None:
        nonlocal caption_started
        if not caption_started:
            print("\n  🎬 Live captions:")
            print("  " + "─" * 66)
            caption_started = True
        print(delta, end="", flush=True)

    # ── Stream → STT ───────────────────────────────────────────────
    print("  🔴 Streaming… (this runs in real-time, unlike batch)")
    chunks = stream_frames(wf, bytes_per_frame, args.chunk_ms, args.speed, args.max_seconds)

    started = asyncio.get_event_loop().time()
    try:
        transcript = await stream_transcribe(
            chunks,
            language=args.language,
            on_delta=on_delta,
        )
    except TranscribeError as exc:
        if caption_started:
            print()
        print(f"\n❌ STT failed ({exc.status_code}): {exc}")
        if exc.status_code in (401, 403):
            print("   → Your VoxTral API key is invalid or expired.")
            print("   → Get a new one at: https://console.mistral.ai/api-keys")
        sys.exit(1)
    finally:
        wf.close()

    elapsed = asyncio.get_event_loop().time() - started
    if caption_started:
        print("\n  " + "─" * 66)
    print(f"\n  ✅ Transcription complete — {len(transcript)} chars in {elapsed:.1f}s wall time")
    print(f"     Preview: {transcript[:200]}{'…' if len(transcript) > 200 else ''}")
    print()

    if args.save_transcript:
        args.save_transcript.write_text(transcript, encoding="utf-8")
        print(f"  💾 Transcript saved to: {args.save_transcript}\n")

    # ── Pipeline ───────────────────────────────────────────────────
    if args.no_pipeline:
        print("  ⏭  Skipping pipeline (--no-pipeline).")
        return

    if not transcript.strip():
        print("  ⚠ Empty transcript — skipping pipeline (call may have been silent).")
        return

    pv = await run_pipeline(transcript, args.date)

    print("\n" + "=" * 70)
    print("  FINAL PV (Procès-Verbal)")
    print("=" * 70)
    if args.json:
        print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))
    else:
        additional_lines = "".join(
            f"\n  👤 Extra:      {p.get('name', '?')} ({p.get('role', '?')})"
            for p in pv.get("additional_participants", [])
        )
        print(f"""
  📋 PV ID:       {pv.get('pv_id', 'N/A')}
  🏷  Call Type:   {pv.get('call_type', 'N/A')}
  📌 Subject:     {pv.get('subject', 'N/A')}
  👤 Left:        {pv.get('left', {}).get('name', '?')} ({pv.get('left', {}).get('role', '?')})
  👤 Right:       {pv.get('right', {}).get('name', '?')} ({pv.get('right', {}).get('role', '?')}){additional_lines}
  📝 Actions:     {len(pv.get('actions', []))}
  📅 Meeting:     {'Yes — ' + str(pv.get('meeting_datetime', '')) if pv.get('meeting_created') else 'No'}

  ── Compte Rendu ──
  {pv.get('compte_rendu', 'N/A')}
""")
        print("  ── Full JSON ──")
        print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))

    print("\n  🎉 Live replay complete!")


if __name__ == "__main__":
    asyncio.run(main())
