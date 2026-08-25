"""Transcription-specific exceptions."""


class TranscribeError(Exception):
    """Raised when transcription fails — API error, bad audio, etc."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
