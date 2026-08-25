"""Transcript merging — interleave labeled segments into one timestamped transcript.

When each meeting member is transcribed by its own independent STT session
(per-device identity, no diarization), the pieces arrive out of order and may
overlap in time. This module takes those labeled segments and produces a single
chronological transcript in the format the summarizer already expects
(``[HH:MM:SS] Speaker : text`` — see INPUT_SCHEMA.md).
"""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Segment:
    """One labeled piece of speech from a single speaker.

    ``ts`` is the number of seconds since the call started (arrival time
    stamped by the session manager). Sorting by it gives chronological order.
    """

    ts: float
    speaker: str
    text: str


def _fmt_ts(seconds: float) -> str:
    """Format a seconds offset as ``HH:MM:SS``."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def interleave_segments(segments: Iterable[Segment]) -> str:
    """Interleave labeled segments chronologically into a transcript.

    Segments are sorted by ``ts`` (stable sort, so ties keep insertion order).
    Returns the ``INPUT_SCHEMA.md`` dialogue format:
        [HH:MM:SS] Speaker : text
    """
    ordered = sorted(segments, key=lambda seg: seg.ts)
    lines = []
    for seg in ordered:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(f"[{_fmt_ts(seg.ts)}] {seg.speaker} : {text}")
    return "\n".join(lines)
