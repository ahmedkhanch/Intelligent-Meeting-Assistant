#!/usr/bin/env python
"""End-to-end pipeline test — audio file all the way to PV + routing.

Takes a .wav (or .mp3) file, transcribes it via Mistral VoxTral STT,
then runs the full AI pipeline: summarizer → classifier → extract → route.

Usage:
  # From generated meeting audio (the real end-to-end)
  python scripts/e2e_test.py --audio tech_meeting_test.wav

  # From a text transcript file (skip STT — like mock_call.py)
  python scripts/e2e_test.py --transcript tests/fixtures/sample_transcript_tech.txt

  # With extra options
  python scripts/e2e_test.py --audio tech_meeting_test.wav --language fr --json

Requirements (all already configured in .env):
  - VOXTRAL_API_KEY  → Mistral STT  (Phase 2)
  - DEEPSEEK_API_KEY → LLM summarization (Phase 1)
"""

import argparse
import asyncio
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.transcription import transcribe_file, TranscribeError
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
logger = logging.getLogger("e2e_test")

# ── CLI ──────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRM Vocal — End-to-End Pipeline Test (Phase 1 + Phase 2)",
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--audio", "-a",
        type=Path,
        help="Path to a .wav or .mp3 audio file → transcribe via VoxTral → pipeline.",
    )
    input_group.add_argument(
        "--transcript", "-t",
        type=Path,
        help="Path to a text transcript file → skip STT, go straight to pipeline.",
    )

    parser.add_argument(
        "--language", "-l",
        type=str,
        default="fr",
        help="Language hint for STT (default: fr).",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable speaker diarization in VoxTral (identifies different speakers).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().isoformat(),
        help="Call date in ISO format (default: now).",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output only the final PV as JSON (useful for piping).",
    )
    parser.add_argument(
        "--save-transcript",
        type=Path,
        default=None,
        help="Save the transcribed text to a file (useful for debugging STT output).",
    )
    return parser.parse_args()


# ── Pipeline ─────────────────────────────────────────────────────────────


async def run_e2e_pipeline(
    transcript: str,
    call_date: str,
    *,
    audio_path: Path | None = None,
) -> dict:
    """Run the full pipeline on a transcript.

    Steps:
        1. Summarizer — transcript → LLM → structured PV
        2. Classifier — validate call type
        3. Action Extractor — validate & enrich tasks
        4. Router — dispatch to HubSpot or Ora Studio

    Args:
        transcript: The full call transcript text.
        call_date: ISO date string.
        audio_path: If provided, used in display headers only.

    Returns:
        The complete PV dict.
    """
    header = f"E2E TEST — {audio_path.name}" if audio_path else "E2E TEST"
    print("=" * 70)
    print(f"  {header}")
    print("=" * 70)
    print(f"  Transcript: {len(transcript)} chars")
    print(f"  Call date:  {call_date}")
    print()

    # ── Step 1: Summarize ───────────────────────────────────────────
    print("─" * 70)
    print("  Step 1/4: SUMMARIZER — sending transcript to DeepSeek...")
    print("─" * 70)
    pv = await summarize(transcript, call_date=call_date)
    print(f"  ✅ PV generated (pv_id: {pv.get('pv_id', 'N/A')})")
    print(f"     Call type (AI):      {pv.get('call_type', 'N/A')}")
    print(f"     Subject:             {pv.get('subject', 'N/A')}")
    print(f"     Actions extracted:   {len(pv.get('actions', []))}")
    print(f"     Meeting scheduled:   {pv.get('meeting_created', False)}")
    print(f"\n     Compte rendu:\n     {pv.get('compte_rendu', 'N/A')}")
    print()

    # ── Step 2: Validate Call Type ───────────────────────────────────
    print("─" * 70)
    print("  Step 2/4: CLASSIFIER — validating call type...")
    print("─" * 70)
    pv["call_type"] = classify(pv.get("call_type"))
    print(f"  ✅ Call type: {pv['call_type']}")
    print()

    # ── Step 3: Extract Actions ─────────────────────────────────────
    print("─" * 70)
    print("  Step 3/4: ACTION EXTRACTOR — validating tasks...")
    print("─" * 70)
    actions = extract(pv)
    pv["actions"] = actions
    print(f"  ✅ {len(actions)} valid action(s):")
    for i, action in enumerate(actions, 1):
        diff = action.get("difficulty", "—")
        model_hint = action.get("model_hint", "—")
        deadline = action.get("deadline", "—")
        print(f"     {i}. [{diff}] {action['title']}")
        print(f"        → {action['owner']}  |  deadline: {deadline}  |  model: {model_hint}")
    print()

    # ── Step 4: Route ───────────────────────────────────────────────
    print("─" * 70)
    print("  Step 4/4: ROUTER — dispatching...")
    print("─" * 70)
    result = await route(pv)
    print(f"  ✅ Routing: {json.dumps(result, indent=4, ensure_ascii=False)}")
    print()

    return pv


# ── Main ─────────────────────────────────────────────────────────────────


async def main() -> None:
    args = parse_args()

    # ── Phase 2: Audio → STT → transcript ────────────────────────────
    if args.audio:
        audio_path = args.audio
        if not audio_path.exists():
            print(f"❌ Audio file not found: {audio_path}")
            sys.exit(1)

        print("=" * 70)
        print(f"  🎤 STT: Transcribing {audio_path.name} ({audio_path.stat().st_size / 1024:.0f} KB)")
        print(f"     Model:    {settings.voxtral_model}")
        print(f"     Language: {args.language}")
        print(f"     Diarize:  {args.diarize}")
        print("=" * 70)

        # Quick pre-flight check
        if not settings.voxtral_api_key:
            print("❌ VOXTRAL_API_KEY is not set in .env — cannot transcribe audio.")
            print("   Get a key at: https://console.mistral.ai/api-keys")
            print("   Or use --transcript to test with a pre-written text file.")
            sys.exit(1)

        try:
            audio_bytes = audio_path.read_bytes()
            transcript = await transcribe_file(
                audio_bytes,
                language=args.language,
                diarize=args.diarize,
            )
        except TranscribeError as exc:
            print(f"\n❌ STT failed ({exc.status_code}): {exc}")
            if exc.status_code in (401, 403):
                print("   → Your VoxTral API key is invalid or expired.")
                print("   → Get a new one at: https://console.mistral.ai/api-keys")
                print("   → Or use --transcript to test with text file instead.")
            sys.exit(1)
        except Exception as exc:
            print(f"\n❌ STT failed (network error): {exc}")
            print("   → Check your internet connection and VOXTRAL_BASE_URL.")
            sys.exit(1)

        print(f"\n✅ Transcription complete — {len(transcript)} chars")
        print(f"   Preview: {transcript[:200]}{'…' if len(transcript) > 200 else ''}")
        print()

        # Save transcript if requested
        if args.save_transcript:
            args.save_transcript.write_text(transcript, encoding="utf-8")
            print(f"💾 Transcript saved to: {args.save_transcript}")

    # ── Phase 1: Transcript → pipeline ──────────────────────────────
    else:
        audio_path = None
        transcript_path = args.transcript
        if not transcript_path.exists():
            print(f"❌ Transcript file not found: {transcript_path}")
            sys.exit(1)

        print(f"📄 Loading transcript from: {transcript_path}")
        transcript = transcript_path.read_text(encoding="utf-8")
        print(f"   {len(transcript)} chars loaded\n")

    # Run the pipeline
    pv = await run_e2e_pipeline(transcript, args.date, audio_path=args.audio)

    # ── Final Output ─────────────────────────────────────────────────
    print("=" * 70)
    print("  FINAL PV (Procès-Verbal)")
    print("=" * 70)
    if args.json:
        print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))
    else:
        # Pretty summary
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
        # Also dump full JSON for inspection
        print("  ── Full JSON ──")
        print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))

    print(f"\n🎉 End-to-end pipeline complete!")


if __name__ == "__main__":
    asyncio.run(main())
