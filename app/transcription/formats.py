"""Audio format definitions and conversion for the transcription pipeline.

Mistral VoxTral realtime expects PCM S16LE, 16000 Hz, mono.
This module defines the target format and provides a conversion bridge.
"""

from dataclasses import dataclass

# ── Target format (what VoxTral expects) ────────────────────────────────

TARGET_ENCODING = "pcm_s16le"
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


@dataclass(frozen=True)
class AudioFormat:
    """Describes an audio stream's encoding properties."""

    encoding: str       # "pcm_s16le", "pcm_f32le", "mp3", etc.
    sample_rate: int    # Hz — 8000, 16000, 44100, 48000, etc.
    channels: int = 1   # 1 = mono, 2 = stereo


def target() -> AudioFormat:
    """Return the audio format VoxTral expects."""
    return AudioFormat(
        encoding=TARGET_ENCODING,
        sample_rate=TARGET_SAMPLE_RATE,
        channels=TARGET_CHANNELS,
    )


def matches_target(fmt: AudioFormat) -> bool:
    """Check if an audio format already matches the VoxTral target."""
    return (
        fmt.encoding == TARGET_ENCODING
        and fmt.sample_rate == TARGET_SAMPLE_RATE
        and fmt.channels == TARGET_CHANNELS
    )


def convert(audio: bytes, from_format: AudioFormat) -> bytes:
    """Convert audio to the target format if needed.

    If the source already matches the target, it passes through unchanged.
    Otherwise, conversion is attempted via available audio libraries.

    Currently a pass-through with a warning — install pydub + ffmpeg
    to enable automatic resampling and format conversion.
    """
    if matches_target(from_format):
        return audio

    # Try conversion via optional dependencies
    try:
        return _convert_via_pydub(audio, from_format)
    except ImportError:
        pass

    try:
        return _convert_numpy(audio, from_format)
    except ImportError:
        pass

    import logging
    logging.getLogger(__name__).warning(
        "Audio format mismatch (got %s/%dHz/%dch, need %s/%dHz/%dch) "
        "but no conversion library is installed. Install pydub for auto-conversion.",
        from_format.encoding, from_format.sample_rate, from_format.channels,
        TARGET_ENCODING, TARGET_SAMPLE_RATE, TARGET_CHANNELS,
    )
    return audio  # pass through and hope for the best


# ── Optional converters ─────────────────────────────────────────────────


def _convert_via_pydub(audio: bytes, fmt: AudioFormat) -> bytes:
    """Convert using pydub (requires ffmpeg on PATH)."""
    from io import BytesIO
    from pydub import AudioSegment  # type: ignore[import-untyped]

    segment = AudioSegment.from_raw(
        BytesIO(audio),
        sample_width=_bytes_per_sample(fmt.encoding),
        frame_rate=fmt.sample_rate,
        channels=fmt.channels,
    )
    # Resample + set channels, then export as raw PCM S16LE
    segment = segment.set_frame_rate(TARGET_SAMPLE_RATE).set_channels(TARGET_CHANNELS)
    buf = BytesIO()
    segment.export(buf, format="s16le")
    return buf.read()


def _convert_numpy(audio: bytes, fmt: AudioFormat) -> bytes:
    """Convert using numpy for basic resampling (linear interpolation)."""
    import numpy as np  # type: ignore[import-untyped]

    # Decode source encoding
    dtype = {"pcm_s16le": np.int16, "pcm_f32le": np.float32}.get(fmt.encoding)
    if dtype is None:
        raise ImportError(f"Unsupported encoding for numpy conversion: {fmt.encoding}")

    samples = np.frombuffer(audio, dtype=dtype)

    # Stereo → mono (average channels)
    if fmt.channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)

    # Resample via linear interpolation
    if fmt.sample_rate != TARGET_SAMPLE_RATE:
        ratio = TARGET_SAMPLE_RATE / fmt.sample_rate
        old_len = len(samples)
        new_len = int(old_len * ratio)
        indices = np.linspace(0, old_len - 1, new_len)
        samples = np.interp(indices, np.arange(old_len), samples.astype(np.float64))

    # Convert back to S16LE
    samples = samples.astype(np.int16)
    return samples.tobytes()


def _bytes_per_sample(encoding: str) -> int:
    return {"pcm_s16le": 2, "pcm_f32le": 4}.get(encoding, 2)
