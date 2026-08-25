"""Ora Studio HTTP client.

Phase 1: Mock client that logs operations.
Phase 2+: Real API calls to Ora Studio with credentials from settings.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OraStudioClient:
    """Async HTTP client for Ora Studio API.

    In Phase 1, all methods are stubs that log what they would do.
    When ORA_STUDIO_API_KEY is configured, they make real API calls.
    """

    def __init__(self) -> None:
        self._mock = not bool(settings.ora_studio_api_key)
        if self._mock:
            logger.info("Ora Studio client running in MOCK mode — no API calls will be made")
        else:
            self._base = settings.ora_studio_api_url.rstrip("/")
            self._headers: dict[str, str] = {}
            logger.info("Ora Studio client running in LIVE mode")

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST to Ora Studio API.

        Args:
            path: API path, e.g. "/api/crm/tasks"
            body: Request body as dict.
        """
        if self._mock:
            logger.info("[MOCK] POST %s → %s", path, _truncate(body))
            return {"status": "ok", "id": "mock-todo-list"}

        self._headers["Authorization"] = f"Bearer {settings.ora_studio_api_key}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}{path}",
                json=body,
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()


# Singleton
ora_studio_client = OraStudioClient()


def _truncate(obj: Any, max_len: int = 200) -> str:
    text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
