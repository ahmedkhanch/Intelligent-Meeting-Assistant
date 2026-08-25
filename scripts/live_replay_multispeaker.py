#!/usr/bin/env python
"""Multi-member live replay — simulate the WebRTC page without a browser.

Each member is a separate audio track with a known identity, so this script
opens **one WebSocket per member** (``/ws/call/{session_id}/{speaker_id}``),
streams that member's own WAV, then signals ``end_call`` and prints the PV the
server broadcasts back.

This exercises the per-device / interruption-tolerant transcription path
(one realtime STT session per member, merged into a labeled transcript).

Usage:
  # Per-speaker WAVs (from scripts/generate_meeting_audio.py --split-speakers)
  python scripts/live_replay_multispeaker.py --dir tests/fixtures/sample_transcript_4person_meeting_speakers

  # Explicit name → file mapping
  python scripts/live_replay_multispeaker.py \
      --speakers "kh=tests/.../kh.wav" "Sami=tests/.../Sami.wav"

Requirements:
  - A running uvicorn server:  uvicorn app.main:app --port 8000
  - VOXTRAL_API_KEY + DEEPSEEK_API_KEY in .env
"""

import argparse
import asyncio
import io
import json
import sys
import wave
from pathlib import Path
from urllib.parse import quote

import websockets

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CRM Vocal — multi-member live replay")
    parser.add_argument("--session-id", default="replay-1", help="Call session id.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--dir", type=Path, help="Directory of {speaker}.wav files.")
    src.add_argument(
        "--speakers",
        nargs="+",
        metavar="NAME=PATH",
        help="Explicit 'speaker=path.wav' pairs.",
    )

    parser.add_argument("--left", help="Comma-separated member names on the Ora side.")
    parser.add_argument("--right", help="Comma-separated member names on the external side.")
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--speed", type=float, default=2.0, help="Playback speed (2 = 2x).")
    return parser.parse_args()


def resolve_speakers(args: argparse.Namespace) -> list[tuple[str, Path]]:
    """Return [(speaker_name, wav_path), ...] from --dir or --speakers."""
    if args.speakers:
        pairs = []
        for item in args.speakers:
            name, _, path = item.partition("=")
            if not name or not path:
                raise SystemExit(f"❌ Bad --speakers item (want NAME=PATH): {item}")
            pairs.append((name, Path(path)))
        return pairs

    wavs = sorted(args.dir.glob("*.wav"))
    if not wavs:
        raise SystemExit(f"❌ No .wav files in {args.dir}")
    return [(p.stem, p) for p in wavs]


async def stream_wav(ws, path: Path, chunk_ms: int, speed: float) -> None:
    """Stream a WAV (PCM S16LE 16 kHz mono) as paced binary frames."""
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        frames_per_chunk = max(1, int(rate * chunk_ms / 1000))
        sleep_s = (chunk_ms / 1000.0) / speed
        while True:
            data = wf.readframes(frames_per_chunk)
            if not data:
                break
            await ws.send(data)
            await asyncio.sleep(sleep_s)


async def recv_until_result(ws, speaker: str) -> dict:
    """Read frames until the server sends pv_result (or error).

    Binary frames are relayed audio from the other members — skip them.
    """
    async for raw in ws:
        if not isinstance(raw, str):
            continue  # relayed audio frame
        payload = json.loads(raw)
        if payload.get("type") in ("pv_result", "error"):
            payload["_speaker"] = speaker
            return payload


async def main() -> None:
    args = parse_args()
    speakers = resolve_speakers(args)

    print("=" * 70)
    print("  MULTI-MEMBER LIVE REPLAY — per-device transcription")
    print("=" * 70)
    print(f"  Session : {args.session_id}")
    print(f"  Members : {len(speakers)}")
    for name, path in speakers:
        print(f"    - {name:<12s} {path}")
    print()

    side_map: dict[str, str] = {}
    for name in (args.left or "").split(","):
        if name.strip():
            side_map[name.strip()] = "left"
    for name in (args.right or "").split(","):
        if name.strip():
            side_map[name.strip()] = "right"

    def uri(speaker: str) -> str:
        url = f"ws://{args.host}:{args.port}/ws/call/{quote(args.session_id)}/{quote(speaker)}"
        side = side_map.get(speaker)
        if side:
            url += f"?side={side}"
        return url

    # Phase 1 — open one WS per member, activate agent listening, then stream
    # each member's own audio.
    print("  🔴 Streaming all members concurrently…")
    connections = await asyncio.gather(
        *[websockets.connect(uri(name)) for name, _ in speakers]
    )
    try:
        await asyncio.gather(
            *[ws.send(json.dumps({"type": "listen_start"})) for ws in connections]
        )
        await asyncio.gather(
            *[
                stream_wav(ws, path, args.chunk_ms, args.speed)
                for ws, (_, path) in zip(connections, speakers)
            ]
        )
        print("  ✅ All audio streamed — sending end_call")

        # Phase 2 — end the call; the server finalizes and broadcasts the PV
        # back over these still-open sockets.
        await asyncio.gather(
            *[ws.send(json.dumps({"type": "end_call"})) for ws in connections]
        )
        results = await asyncio.gather(
            *[recv_until_result(ws, name) for ws, (name, _) in zip(connections, speakers)]
        )
    finally:
        await asyncio.gather(*[ws.close() for ws in connections], return_exceptions=True)

    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    for r in results:
        if r is None:
            continue
        print(f"\n── member {r.get('_speaker')} received ──")
        if r.get("type") == "error":
            print(json.dumps(r, ensure_ascii=False, indent=2))
            continue
        pv = r.get("pv", {})
        extra = ", ".join(p.get("name", "?") for p in pv.get("additional_participants", []))
        print(f"  call_type   : {pv.get('call_type')}")
        print(f"  left        : {pv.get('left', {}).get('name')} ({pv.get('left', {}).get('side')})")
        print(f"  right       : {pv.get('right', {}).get('name')} ({pv.get('right', {}).get('side')})")
        print(f"  extra       : {extra or '—'}")
        print(f"  actions     : {len(pv.get('actions', []))}")
        print(f"  routing     : {json.dumps(r.get('routing'), ensure_ascii=False)}")

    print("\n  🎉 Multi-member replay complete!")


if __name__ == "__main__":
    asyncio.run(main())
