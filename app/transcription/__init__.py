"""Transcription package — Mistral VoxTral STT.

Two modes:
- Batch:  transcribe_file()  — upload full audio file, get text back
- Stream: stream_transcribe() — push audio chunks in real-time, get the full
  transcript back (optional on_delta callback receives live text deltas)

Audio format helpers:
- AudioFormat, target(), matches_target(), convert()
"""

from app.transcription.client import transcribe_file
from app.transcription.errors import TranscribeError
from app.transcription.formats import AudioFormat, convert, matches_target, target
from app.transcription.realtime import stream_transcribe

__all__ = [
    "transcribe_file",
    "stream_transcribe",
    "TranscribeError",
    "AudioFormat",
    "target",
    "matches_target",
    "convert",
]
