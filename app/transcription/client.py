"""REST client for Mistral VoxTral batch transcription.

Sends an audio file to POST /v1/audio/transcriptions and returns the text.
"""

import logging

import httpx

from app.config import settings
from app.transcription.errors import TranscribeError

logger = logging.getLogger(__name__)

# ── Public API ──────────────────────────────────────────────────────────


async def transcribe_file(
    audio: bytes,
    *,
    language: str | None = None,
    diarize: bool = False,
) -> str:
    """Transcribe an audio file via Mistral's batch STT endpoint.

    Args:
        audio: Raw audio bytes (WAV, MP3, etc.).
        language: ISO language code (e.g. "fr", "en"). Auto-detected if None.
        diarize: Whether to identify different speakers.

    Returns:
        The transcribed text.

    Raises:
        TranscribeError: On API error or non-200 response.
    """
    url = f"{settings.voxtral_base_url}/v1/audio/transcriptions"

    data: dict = {"model": settings.voxtral_model}
    if language:
        data["language"] = language
    if diarize:
        data["diarize"] = "true"
        # Mistral requires timestamp_granularities=["segment"] when diarize is enabled
        # in batch (non-streaming) mode — otherwise 422.
        data["timestamp_granularities"] = ["segment"]

    logger.info("Transcribing %d bytes via Mistral STT (model=%s)", len(audio), settings.voxtral_model)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.voxtral_api_key}"},
            files={"file": ("audio.wav", audio, "audio/wav")},
            data=data,
        )

    if response.status_code != 200:
        raise TranscribeError(
            f"Mistral STT returned {response.status_code}: {response.text[:500]}",
            status_code=response.status_code,
        )

    result = response.json()
    text = result.get("text", "")
    logger.info("Transcription complete — %d chars", len(text))
    return text
