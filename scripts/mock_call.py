#!/usr/bin/env python
"""Mock Call Script — Phase 1 pipeline runner.

Feeds a transcript text file through the full AI + routing pipeline:
    summarizer → classifier → action_extractor → router → HubSpot | Ora Studio

Usage:
    python scripts/mock_call.py --file tests/fixtures/sample_transcript_tech.txt
    python scripts/mock_call.py --file tests/fixtures/sample_transcript_commercial.txt
    python scripts/mock_call.py --text "raw transcript text here..."

Simulates what Ahmed's WebSocket will deliver in Phase 2.
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

from app.agent.summarizer import summarize
from app.agent.classifier import classify
from app.agent.action_extractor import extract
from app.routing.router import route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock_call")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CRM Vocal — Mock Call Pipeline (Phase 1)",
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--file", "-f",
        type=Path,
        help="Path to a transcript text file",
    )
    input_group.add_argument(
        "--text", "-t",
        type=str,
        help="Raw transcript text (useful for quick tests)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().isoformat(),
        help="Call date in ISO format (default: now)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="DeepSeek model override (default: from .env)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output the final PV as JSON only (useful for piping)",
    )
    return parser.parse_args()


async def run_pipeline(transcript: str, call_date: str, model: str | None = None) -> dict:
    """Run the full Phase 1 pipeline on a transcript.

    Steps:
        1. Summarizer — sends transcript to DeepSeek, returns PV JSON
        2. Classifier — auto-detects call type from PV content
        3. Action Extractor — validates and enriches actions/todos
        4. Router — dispatches to HubSpot or Ora Studio
    """
    print("=" * 70)
    print("  CRM VOCAL — Phase 1 Pipeline")
    print("=" * 70)
    print(f"\n📄 Transcript: {len(transcript)} chars")
    print(f"📅 Call date:  {call_date}")
    print()

    # ── Step 1: Summarize ───────────────────────────────────────────
    print("─" * 70)
    print("  Step 1/4: SUMMARIZER — sending to DeepSeek...")
    print("─" * 70)
    pv = await summarize(transcript, call_date=call_date, model=model)
    print(f"\n✅ PV generated (pv_id: {pv.get('pv_id', 'N/A')})")
    print(f"   Call type (from AI):  {pv.get('call_type', 'N/A')}")
    print(f"   Subject:              {pv.get('subject', 'N/A')}")
    print(f"   Left participant:     {pv.get('left', {}).get('name', '?')}")
    print(f"   Right participant:    {pv.get('right', {}).get('name', '?')}")
    additional = pv.get("additional_participants", [])
    if additional:
        print(f"   Other participants:   {', '.join(p.get('name', '?') for p in additional)}")
    print(f"   Actions extracted:    {len(pv.get('actions', []))}")
    print(f"   Meeting scheduled:    {pv.get('meeting_created', False)}")
    print(f"\n   Compte rendu:")
    print(f"   {pv.get('compte_rendu', 'N/A')}")
    print()

    # ── Step 2: Validate Call Type ───────────────────────────────────
    print("─" * 70)
    print("  Step 2/4: VALIDATE — checking LLM call type...")
    print("─" * 70)
    pv["call_type"] = classify(pv.get("call_type"))  # validate LLM classification
    print(f"\n✅ Call type validated: {pv['call_type']}")
    print()

    # ── Step 3: Extract Actions ─────────────────────────────────────
    print("─" * 70)
    print("  Step 3/4: ACTION EXTRACTOR — validating tasks...")
    print("─" * 70)
    actions = extract(pv)
    pv["actions"] = actions
    print(f"\n✅ {len(actions)} valid action(s):")
    for i, action in enumerate(actions, 1):
        diff = action.get('difficulty', '—')
        model = action.get('model_hint', '—')
        deadline = action.get('deadline', '—')
        print(f"   {i}. [{diff}] {action['title']}")
        print(f"      → {action['owner']}  |  deadline: {deadline}  |  model: {model}")
    print()

    # ── Step 4: Route ───────────────────────────────────────────────
    print("─" * 70)
    print("  Step 4/4: ROUTER — dispatching...")
    print("─" * 70)
    result = await route(pv)
    print(f"\n✅ Routing result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    print()

    # ── Final PV ────────────────────────────────────────────────────
    print("=" * 70)
    print("  FINAL PV (Procès-Verbal)")
    print("=" * 70)
    print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))
    print()

    return pv


def main() -> None:
    args = parse_args()

    # Read transcript
    if args.file:
        transcript = args.file.read_text(encoding="utf-8")
        logger.info("Loaded transcript from %s (%d chars)", args.file, len(transcript))
    else:
        transcript = args.text
        logger.info("Using inline transcript (%d chars)", len(transcript))

    # Run the pipeline
    pv = asyncio.run(run_pipeline(transcript, args.date, args.model))

    # JSON-only output mode
    if args.json:
        print(json.dumps(pv, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
