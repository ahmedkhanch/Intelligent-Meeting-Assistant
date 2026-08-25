"""HubSpot HTTP client — OAuth2 authenticated requests.

Phase 1: Mock client that logs operations.
Phase 2+: Real HubSpot API calls with credentials from settings.
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class HubSpotClient:
    """Async HTTP client for HubSpot CRM API v3.

    In Phase 1, all methods are stubs that log what they would do.
    When HUBSPOT_CLIENT_ID is configured, they make real API calls.
    """

    def __init__(self) -> None:
        self._mock = not (
            settings.hubspot_access_token
            or settings.hubspot_client_id
        )
        if self._mock:
            logger.info("HubSpot client running in MOCK mode — no API calls will be made")
        else:
            self._base = "https://api.hubapi.com"
            self._headers: dict[str, str] = {}
            logger.info("HubSpot client running in LIVE mode")

    async def _ensure_auth(self) -> None:
        """Set Bearer auth header.

        Uses the Personal Access Token (PAT) if available,
        otherwise falls back to OAuth2 refresh token flow (Phase 3).
        """
        if self._mock:
            return
        if settings.hubspot_access_token:
            # PAT — simple Bearer token, no OAuth needed
            self._headers["Authorization"] = f"Bearer {settings.hubspot_access_token}"
        else:
            # OAuth2 — use refresh token (Phase 2+: implement token refresh)
            self._headers["Authorization"] = f"Bearer {settings.hubspot_refresh_token}"

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST to HubSpot API.

        Args:
            path: API path, e.g. "/crm/v3/objects/notes"
            body: Request body as dict.
        """
        if self._mock:
            logger.info("[MOCK] POST %s → %s", path, _truncate(body))
            return {"id": "mock-id", "properties": body}

        await self._ensure_auth()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base}{path}",
                json=body,
                headers=self._headers,
                timeout=30,
            )
            if resp.is_error:
                logger.error(
                    "HubSpot POST %s → %d %s\n  Request: %s\n  Response: %s",
                    path,
                    resp.status_code,
                    resp.reason_phrase,
                    _truncate(body),
                    resp.text[:1000],
                )
            resp.raise_for_status()
            return resp.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET from HubSpot API.

        Args:
            path: API path, e.g. "/crm/v3/owners"
            params: Optional query parameters.
        """
        if self._mock:
            logger.info("[MOCK] GET %s", path)
            return {"results": []}

        await self._ensure_auth()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base}{path}",
                params=params,
                headers=self._headers,
                timeout=30,
            )
            if resp.is_error:
                logger.error(
                    "HubSpot GET %s → %d %s\n  Response: %s",
                    path,
                    resp.status_code,
                    resp.reason_phrase,
                    resp.text[:1000],
                )
            resp.raise_for_status()
            return resp.json()

    async def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """PUT to HubSpot API.

        Args:
            path: API path, e.g. "/crm/v3/objects/deals/{id}/associations/..."
            body: Optional request body.
        """
        if self._mock:
            logger.info("[MOCK] PUT %s → %s", path, _truncate(body or {}))
            return {"id": "mock-id"}

        await self._ensure_auth()
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self._base}{path}",
                json=body,
                headers=self._headers,
                timeout=30,
            )
            if resp.is_error:
                logger.error(
                    "HubSpot PUT %s → %d %s\n  Request: %s\n  Response: %s",
                    path,
                    resp.status_code,
                    resp.reason_phrase,
                    _truncate(body or {}),
                    resp.text[:1000],
                )
            resp.raise_for_status()
            return resp.json()

    async def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """PATCH to HubSpot API."""
        if self._mock:
            logger.info("[MOCK] PATCH %s → %s", path, _truncate(body))
            return {"id": "mock-id", "properties": body}

        await self._ensure_auth()
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{self._base}{path}",
                json=body,
                headers=self._headers,
                timeout=30,
            )
            if resp.is_error:
                logger.error(
                    "HubSpot PATCH %s → %d %s\n  Request: %s\n  Response: %s",
                    path,
                    resp.status_code,
                    resp.reason_phrase,
                    _truncate(body),
                    resp.text[:1000],
                )
            resp.raise_for_status()
            return resp.json()


# Singleton
hubspot_client = HubSpotClient()


def _truncate(obj: Any, max_len: int = 200) -> str:
    text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
