"""Tests for transcript merging (app/transcription/merge.py)."""

from app.transcription.merge import Segment, interleave_segments


def test_interleaves_by_timestamp():
    segments = [
        Segment(ts=3.0, speaker="Lina", text="Troisième"),
        Segment(ts=1.0, speaker="Sami", text="Premier"),
        Segment(ts=2.0, speaker="kh", text="Deuxième"),
    ]
    out = interleave_segments(segments)
    lines = out.split("\n")
    assert lines[0].startswith("[00:00:01] Sami : Premier")
    assert lines[1].startswith("[00:00:02] kh : Deuxième")
    assert lines[2].startswith("[00:00:03] Lina : Troisième")


def test_stable_ordering_for_equal_timestamps():
    segments = [
        Segment(ts=1.0, speaker="A", text="un"),
        Segment(ts=1.0, speaker="B", text="deux"),
    ]
    out = interleave_segments(segments)
    # stable sort keeps insertion order on ties
    assert out.split("\n")[0].startswith("[00:00:01] A : un")
    assert out.split("\n")[1].startswith("[00:00:01] B : deux")


def test_skips_empty_text():
    segments = [
        Segment(ts=1.0, speaker="Sami", text="   "),
        Segment(ts=2.0, speaker="kh", text="Vrai texte"),
    ]
    out = interleave_segments(segments)
    assert "Sami" not in out
    assert "kh" in out


def test_timestamp_formatting_rolls_over_minutes_and_hours():
    segments = [Segment(ts=3661.0, speaker="kh", text="bout")]
    assert interleave_segments(segments).startswith("[01:01:01] kh : bout")


def test_empty_input_returns_empty_string():
    assert interleave_segments([]) == ""
