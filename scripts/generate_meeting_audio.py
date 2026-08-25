"""
Generate an audio simulation of a meeting from a transcript file.

Uses Microsoft Edge TTS (free, no API key) to synthesize each speaker's lines
with distinct voices, then stitches them together into a single audio file.

Usage:
  python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_tech.txt
  python scripts/generate_meeting_audio.py --file tests/fixtures/sample_transcript_commercial.txt -o meeting.mp3

Requirements:
  pip install edge-tts pydub
  ffmpeg must be on PATH  (install: winget install ffmpeg, or choco install ffmpeg)

Speaker-to-voice mapping is configured below — edit SPEAKER_VOICES to match
the speaker names in your transcripts.
"""

import argparse
import asyncio
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import edge_tts

# ---------------------------------------------------------------------------
# Locate ffmpeg on Windows (common install locations)
# ---------------------------------------------------------------------------
_FFMPEG = shutil.which("ffmpeg")
if _FFMPEG is None and sys.platform == "win32":
    _CANDIDATES = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\Common Files\AEJuice\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
    ]
    for _c in _CANDIDATES:
        if os.path.isfile(_c):
            _FFMPEG = _c
            break

# NOTE: We bypass pydub for audio stitching.  See stitch_mp3s() which uses
# subprocess to call ffmpeg directly via the concat demuxer.  pydub is only
# kept as an optional dependency for future format-conversion needs.
# The _FFMPEG path (above) is used directly by stitch_mp3s().

# Fix Windows console encoding for emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Configuration — map transcript speaker names to edge-tts voices
# ---------------------------------------------------------------------------
# Available French voices (from scripts/list_fr_voices.py):
#   fr-FR-DeniseNeural          Female   French (France)
#   fr-FR-EloiseNeural          Female   French (France)
#   fr-FR-HenriNeural           Male     French (France)
#   fr-FR-RemyMultilingualNeural Male    French (France)
#   fr-FR-VivienneMultilingualNeural Female French (France)
#   fr-BE-CharlineNeural        Female   French (Belgium)
#   fr-BE-GerardNeural          Male     French (Belgium)
#   fr-CA-AntoineNeural         Male     French (Canada)
#   fr-CA-SylvieNeural          Female   French (Canada)
#   fr-CH-ArianeNeural          Female   French (Switzerland)

SPEAKER_VOICES: dict[str, str] = {
    # --- Tech call speakers ---
    "kh": "fr-FR-HenriNeural",
    "Oussema": "fr-FR-DeniseNeural",
    # --- Commercial call speakers ---
    "Ahmed": "fr-FR-HenriNeural",
    "Mehdi Trabelsi": "fr-FR-RemyMultilingualNeural",
    # --- Ambiguous / mixed call speakers ---
    "Karim Mansouri": "fr-FR-DeniseNeural",
    # --- 4-person meeting speakers (multi-participant test) ---
    "Sami": "fr-FR-RemyMultilingualNeural",
    "Lina": "fr-FR-EloiseNeural",
}

# Fallback voices, cycled through for any unknown speaker
FALLBACK_VOICES = [
    "fr-FR-HenriNeural",
    "fr-FR-DeniseNeural",
    "fr-FR-EloiseNeural",
    "fr-FR-RemyMultilingualNeural",
]

# Silence between speaker turns (milliseconds)
TURN_GAP_MS = 600

# Silence after APPEL DÉMARRÉ / before APPEL TERMINÉ markers
MARKER_GAP_MS = 400

# TTS speed adjustment: "+20%" = faster, "-10%" = slower, "0%" = default
TTS_RATE = "+5%"  # slightly faster for natural pacing

# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

LINE_RE = re.compile(
    r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s+(?P<speaker>.+?)\s*:\s*(?P<text>.+)$"
)
MARKER_RE = re.compile(r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s+(?P<text>APPEL (DÉMARRÉ|TERMINÉ))$")


def parse_transcript(path: str) -> list[dict]:
    """Parse a timestamped transcript file into a list of utterances.

    Each utterance: {"speaker": str, "text": str, "ts": str, "is_marker": bool}
    """
    utterances: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue

            # Check for APPEL DÉMARRÉ / APPEL TERMINÉ markers
            m_marker = MARKER_RE.match(line)
            if m_marker:
                utterances.append({
                    "speaker": "system",
                    "text": m_marker.group("text"),
                    "ts": m_marker.group("ts"),
                    "is_marker": True,
                })
                continue

            # Regular dialogue line
            m_line = LINE_RE.match(line)
            if m_line:
                utterances.append({
                    "speaker": m_line.group("speaker").strip(),
                    "text": m_line.group("text").strip(),
                    "ts": m_line.group("ts"),
                    "is_marker": False,
                })
            else:
                # Unrecognised line — treat as narration (single voice)
                utterances.append({
                    "speaker": "system",
                    "text": line.lstrip("[0123456789: ]"),
                    "ts": "",
                    "is_marker": True,
                })

    return utterances


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------

_voice_cycle_index = 0


def get_voice(speaker: str) -> str:
    """Return the edge-tts voice ShortName for *speaker*."""
    global _voice_cycle_index
    if speaker in SPEAKER_VOICES:
        return SPEAKER_VOICES[speaker]
    # Unknown speaker — assign from fallback pool round-robin
    voice = FALLBACK_VOICES[_voice_cycle_index % len(FALLBACK_VOICES)]
    _voice_cycle_index += 1
    print(f"  ⚠ Unknown speaker '{speaker}' → using {voice}")
    return voice


# ---------------------------------------------------------------------------
# TTS synthesis
# ---------------------------------------------------------------------------

async def synthesize_line(
    text: str,
    voice: str,
    rate: str = TTS_RATE,
) -> bytes:
    """Synthesise a single line of speech with edge-tts, return MP3 bytes."""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
    )
    mp3_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_chunks.append(chunk["data"])
    return b"".join(mp3_chunks)


async def generate_silence_mp3(duration_ms: int) -> bytes:
    """Generate an MP3 containing *duration_ms* of silence.

    We synthesise a single space character then pad with silence via pydub,
    or return empty bytes if ffmpeg is unavailable (graceful degradation).
    """
    # edge-tts won't synthesise empty text, so we create a minimal utterance
    # and replace it with silence using pydub.
    communicate = edge_tts.Communicate(text=" ", voice="fr-FR-HenriNeural")
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    if not chunks:
        return b""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(b"".join(chunks)))
        silence = AudioSegment.silent(duration=duration_ms)
        buf = io.BytesIO()
        silence.export(buf, format="mp3")
        return buf.read()
    except Exception:
        return b""  # ffmpeg unavailable — skip silence


async def synthesize_all(
    utterances: list[dict],
    output_dir: Path,
    gap_ms: int = TURN_GAP_MS,
    tts_rate: str = TTS_RATE,
) -> list[bytes]:
    """Synthesise every utterance, return ordered list of MP3 byte strings."""
    mp3_segments: list[bytes] = []
    total = len(utterances)

    for i, utt in enumerate(utterances):
        speaker = utt["speaker"]
        text = utt["text"]
        ts = utt["ts"]
        is_marker = utt["is_marker"]

        if is_marker:
            prefix = "📢" if "DÉMARRÉ" in text else "🏁"
            label = text
        else:
            prefix = "  "
            label = f"{speaker}: {text[:60]}{'…' if len(text) > 60 else ''}"

        print(f"[{i+1:3d}/{total}] {prefix} {label}")

        if is_marker:
            # Markers spoken with a neutral voice at default rate
            mp3_data = await synthesize_line(text, voice="fr-FR-HenriNeural", rate="+0%")
            mp3_segments.append(mp3_data)
            gap = await generate_silence_mp3(MARKER_GAP_MS)
            if gap:
                mp3_segments.append(gap)
        else:
            voice = get_voice(speaker)
            mp3_data = await synthesize_line(text, voice=voice, rate=tts_rate)
            mp3_segments.append(mp3_data)
            gap = await generate_silence_mp3(gap_ms)
            if gap:
                mp3_segments.append(gap)

    return mp3_segments


# ---------------------------------------------------------------------------
# Audio stitching
# ---------------------------------------------------------------------------

def stitch_mp3s(segments: list[bytes], output_path: Path) -> None:
    """Concatenate MP3 segments into a single file.

    Two strategies, tried in order:
    1. ffmpeg concat demuxer — clean, proper re-encode (requires ffmpeg).
    2. Raw binary concatenation — works for most MP3 players.
    """
    segments = [s for s in segments if s]

    if not segments:
        print("❌ No audio generated — check transcript format.")
        sys.exit(1)

    # Strategy 1 — ffmpeg concat demuxer (clean, gapless)
    if _FFMPEG:
        try:
            # Write all segments to temporary files for the concat demuxer
            tmpdir = tempfile.mkdtemp(prefix="meeting_audio_")
            filelist_path = os.path.join(tmpdir, "files.txt")
            with open(filelist_path, "w", encoding="utf-8") as fh:
                for i, seg in enumerate(segments):
                    seg_path = os.path.join(tmpdir, f"seg_{i:04d}.mp3")
                    with open(seg_path, "wb") as sfh:
                        sfh.write(seg)
                    # ffmpeg concat file format — needs absolute or properly-quoted paths
                    fh.write(f"file '{seg_path}'\n")

            # Use ffmpeg concat demuxer + re-encode for clean results
            cmd = [
                _FFMPEG, "-y",
                "-f", "concat", "-safe", "0",
                "-i", filelist_path,
                "-codec:a", "libmp3lame", "-b:a", "64k",
                str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                size_kb = output_path.stat().st_size / 1024
                print(f"\n✅ Audio written to: {output_path}  ({size_kb:.1f} KB)")
                # Cleanup temp files
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                return
            else:
                print(f"  ⚠ ffmpeg concat failed: {result.stderr[:200]}")
        except Exception as err:
            print(f"  ⚠ ffmpeg stitch failed ({err}) — falling back to raw concat…")

    # Strategy 2 — raw binary concatenation
    combined_bytes = b"".join(segments)
    output_path.write_bytes(combined_bytes)
    print(f"\n✅ Audio written to: {output_path}  ({len(combined_bytes) / 1024:.1f} KB)")
    print("  ⚠ Raw MP3 concat — some players may show slight glitches at transitions.")


def convert_to_wav(mp3_path: Path, wav_path: Path) -> bool:
    """Convert MP3 to WAV (PCM S16LE, 16kHz, mono) — ready for VoxTral STT."""
    if not _FFMPEG:
        print("  ⚠ ffmpeg not found — skipping WAV conversion.")
        return False
    cmd = [
        _FFMPEG, "-y",
        "-i", str(mp3_path),
        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        size_kb = wav_path.stat().st_size / 1024
        print(f"  ✅ WAV (16kHz mono): {wav_path}  ({size_kb:.1f} KB)")
        return True
    else:
        print(f"  ⚠ WAV conversion failed: {result.stderr[:200]}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _slugify_speaker(name: str) -> str:
    """Make a speaker name safe for a filename."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "speaker"


async def main():
    # Resolve defaults from module-level constants
    _default_gap = TURN_GAP_MS
    _default_rate = TTS_RATE

    parser = argparse.ArgumentParser(
        description="Generate a simulated meeting audio file from a transcript."
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to the transcript file (timestamped dialogue format).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output MP3 path (default: <transcript_name>_meeting.mp3).",
    )
    parser.add_argument(
        "--gap", "-g",
        type=int,
        default=_default_gap,
        help=f"Silence between speaker turns in ms (default: {_default_gap}).",
    )
    parser.add_argument(
        "--rate", "-r",
        default=_default_rate,
        help=f"TTS speed adjustment e.g. '+10%%' or '-5%%' (default: {_default_rate}).",
    )
    parser.add_argument(
        "--format",
        choices=["mp3", "wav", "both"],
        default="mp3",
        help="Output format: mp3 (default), wav (16kHz mono PCM — for STT), or both.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List available French voices and exit.",
    )
    parser.add_argument(
        "--split-speakers",
        action="store_true",
        help=(
            "Instead of one combined file, write one WAV per speaker into a "
            "directory (for multi-member / per-device replay)."
        ),
    )
    args = parser.parse_args()

    if args.list_voices:
        voices = await edge_tts.list_voices()
        fr = [v for v in voices if v["Locale"].startswith("fr")]
        for v in sorted(fr, key=lambda x: x["ShortName"]):
            print(f"  {v['ShortName']:35s} {v['Gender']:10s} {v['FriendlyName']}")
        return

    # Override module-level settings from CLI
    gap_ms = args.gap
    tts_rate = args.rate

    transcript_path = Path(args.file)
    if not transcript_path.exists():
        print(f"❌ File not found: {transcript_path}")
        sys.exit(1)

    output_ext = ".wav" if args.format == "wav" else ".mp3"
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(str(transcript_path).replace(".txt", f"_meeting{output_ext}"))

    # Always stitch to MP3 first, then convert to WAV if requested
    mp3_path = output_path if output_path.suffix.lower() == ".mp3" else output_path.with_suffix(".mp3")

    print(f"📄 Transcript : {transcript_path}")
    print(f"🎙  Voices     : {len(SPEAKER_VOICES)} configured speakers")
    print(f"⏱  Turn gap   : {gap_ms} ms")
    print(f"⚡ TTS rate    : {tts_rate}")
    print(f"💾 Output     : {output_path}")
    print()

    # Parse
    utterances = parse_transcript(str(transcript_path))
    if not utterances:
        print("❌ No dialogue lines found in transcript.")
        sys.exit(1)
    print(f"📝 Parsed {len(utterances)} utterances\n")

    # ── Per-speaker split (multi-member / per-device replay) ──────────
    if args.split_speakers:
        by_speaker: dict[str, list[dict]] = {}
        for u in utterances:
            if not u["is_marker"]:
                by_speaker.setdefault(u["speaker"], []).append(u)

        if not by_speaker:
            print("❌ No dialogue lines found for per-speaker split.")
            sys.exit(1)

        out_dir = Path(str(transcript_path).replace(".txt", "_speakers"))
        out_dir.mkdir(parents=True, exist_ok=True)

        for speaker, utts in by_speaker.items():
            slug = _slugify_speaker(speaker)
            wav_path = out_dir / f"{slug}.wav"
            mp3_path = out_dir / f"{slug}.mp3"
            print(f"\n🎙  Speaker '{speaker}' — {len(utts)} line(s)")
            segs = await synthesize_all(utts, Path(tempfile.mkdtemp()), gap_ms=gap_ms, tts_rate=tts_rate)
            stitch_mp3s(segs, mp3_path)
            convert_to_wav(mp3_path, wav_path)
            try:
                mp3_path.unlink(missing_ok=True)
            except Exception:
                pass

        print(f"\n✅ Per-speaker WAVs written to: {out_dir}")
        return

    # Synthesise
    print("🔊 Generating speech (this may take a minute)…\n")
    segments = await synthesize_all(utterances, Path(tempfile.mkdtemp()), gap_ms=gap_ms, tts_rate=tts_rate)

    # Stitch → MP3
    print("\n🔗 Stitching audio segments…")
    stitch_mp3s(segments, mp3_path)

    # Convert to WAV if requested (for STT pipeline)
    if args.format in ("wav", "both"):
        wav_path = output_path if output_path.suffix.lower() == ".wav" else output_path.with_suffix(".wav")
        convert_to_wav(mp3_path, wav_path)
        if args.format == "wav":
            # Clean up intermediate MP3 when only WAV was requested
            try:
                mp3_path.unlink(missing_ok=True)
            except Exception:
                pass

    # Summary
    speakers_seen = {u["speaker"] for u in utterances if not u["is_marker"]}
    voices_used = {get_voice(s) for s in speakers_seen}
    print(f"\n📊 Summary:")
    print(f"   Speakers: {', '.join(sorted(speakers_seen))}")
    print(f"   Voices:   {', '.join(sorted(voices_used))}")
    print(f"   Lines:    {len([u for u in utterances if not u['is_marker']])}")
    print(f"\n🎧 Ready to play! Open: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
