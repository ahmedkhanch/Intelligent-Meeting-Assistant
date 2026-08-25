"""Tests for transcription helpers — formats and realtime event parsing."""

import pytest

from app.config import settings
from app.transcription.errors import TranscribeError
from app.transcription.formats import (
    TARGET_CHANNELS,
    TARGET_ENCODING,
    TARGET_SAMPLE_RATE,
    AudioFormat,
    convert,
    matches_target,
    target,
)
from app.transcription.realtime import _build_url, _parse_event


def test_target_returns_voxral_expected_format():
    fmt = target()
    assert fmt.encoding == TARGET_ENCODING
    assert fmt.sample_rate == TARGET_SAMPLE_RATE
    assert fmt.channels == TARGET_CHANNELS


def test_matches_target_true():
    assert matches_target(target()) is True


def test_matches_target_false_on_sample_rate():
    fmt = AudioFormat(TARGET_ENCODING, 44100, TARGET_CHANNELS)
    assert matches_target(fmt) is False


def test_matches_target_false_on_channels():
    fmt = AudioFormat(TARGET_ENCODING, TARGET_SAMPLE_RATE, 2)
    assert matches_target(fmt) is False


def test_convert_passes_through_when_already_target():
    audio = b"\x00\x01\x02\x03"
    assert convert(audio, target()) == audio


def test_transcribe_error_carries_status_code():
    err = TranscribeError("boom", status_code=422)
    assert str(err) == "boom"
    assert err.status_code == 422


def test_transcribe_error_defaults_status_code():
    err = TranscribeError("boom")
    assert err.status_code is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"type": "transcription.text.delta", "text": "bonjour"}', ("delta", "bonjour")),
        ('{"type": "transcription.done", "text": "final"}', ("done", "final")),
        ('{"type": "transcription.segment", "text": "x"}', ("segment", "x")),
        ('{"type": "transcription.language", "audio_language": "fr"}', (None, "")),
        ('{"type": "error", "error": {"message": "bad"}}', (None, "")),
        ('{"type": "session.created"}', (None, "")),
        ("not json", (None, "")),
    ],
)
def test_parse_event(raw, expected):
    assert _parse_event(raw) == expected


def test_build_url_is_secure_websocket_with_model(monkeypatch):
    monkeypatch.setattr(settings, "voxtral_base_url", "https://api.mistral.ai")
    monkeypatch.setattr(settings, "voxtral_realtime_model", "model-x")
    url = _build_url()
    assert url == "wss://api.mistral.ai/v1/audio/transcriptions/realtime?model=model-x"


def test_build_url_handles_http_base(monkeypatch):
    monkeypatch.setattr(settings, "voxtral_base_url", "http://localhost:8080")
    monkeypatch.setattr(settings, "voxtral_realtime_model", "m")
    assert _build_url().startswith("ws://localhost:8080/")
