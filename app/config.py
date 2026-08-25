"""Application configuration — loaded from .env."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All settings are loaded from .env / environment variables."""

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://crm_vocal:crm_vocal@localhost:5432/crm_vocal"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # HubSpot
    hubspot_access_token: str = ""     # PAT (Personal Access Token) — preferred
    hubspot_client_id: str = ""
    hubspot_client_secret: str = ""
    hubspot_refresh_token: str = ""
    hubspot_portal_id: str = "148709607"

    # Ora Studio
    ora_studio_api_url: str = "https://api.ora.studio"
    ora_studio_api_key: str = ""

    # VoxTral (Mistral STT — transcription)
    voxtral_api_key: str = ""
    voxtral_base_url: str = "https://api.mistral.ai"
    voxtral_model: str = "voxtral-mini-latest"                      # batch STT
    voxtral_realtime_model: str = "voxtral-mini-transcribe-realtime-2602"  # realtime STT

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Fallback store — JSON persistence used when Ora Studio is unavailable.
    # Override to a Docker volume path (e.g. /data/fallback_pvs.json); empty = default.
    fallback_store_path: str = ""

    # Multi-member calls (per-device transcription)
    call_end_grace_seconds: float = 5.0   # wait after last member leaves before finalizing
    max_members_per_call: int = 8         # sanity cap on concurrent members per call

    # Incremental pipeline — run the summarizer periodically while the call is
    # still live, so a draft PV exists by the time the meeting ends.
    # NOTE: this is the PV *draft* cadence, NOT the transcription rate —
    # transcription streams in real time via Mistral deltas. The loop only
    # summarizes when the transcript has grown since the last draft, so a
    # shorter interval just makes drafts feel more responsive (no extra LLM
    # calls while the call is silent).
    pipeline_interval_seconds: float = 12.0  # refresh cadence for the live draft
    pipeline_min_chars: int = 300            # don't summarize before this much transcript

    # Realtime STT resilience — how long to wait before reconnecting to Mistral
    # after a dropped connection (or an end-of-utterance endpoint) so a live
    # call keeps transcribing instead of silently stopping.
    stt_reconnect_delay_seconds: float = 1.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
