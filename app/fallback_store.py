"""Fallback store — local JSON-file-backed storage for tech-call PVs and todos.

Serves as the temporary destination when Ora Studio is unavailable (mock mode).
Data persists in ui-next/data/fallback_pvs.json so the Next.js UI can also read it
directly, or consume it via the /api/fallback/* REST endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Store file lives next to the Next.js app so both can access it.
# Overridable via FALLBACK_STORE_PATH (e.g. a Docker volume path).
STORE_PATH = (
    Path(settings.fallback_store_path)
    if settings.fallback_store_path
    else Path(__file__).resolve().parent.parent / "ui-next" / "data" / "fallback_pvs.json"
)
STORE_DIR = STORE_PATH.parent

_lock = asyncio.Lock()


def _ensure_store() -> None:
    """Create the store directory and file if they don't exist."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("{}", encoding="utf-8")


def _read_store() -> dict[str, dict[str, Any]]:
    """Read the full store from disk."""
    _ensure_store()
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupted fallback store — resetting")
        return {}


def _write_store(data: dict[str, dict[str, Any]]) -> None:
    """Write the full store to disk."""
    _ensure_store()
    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ── Public API ──────────────────────────────────────────────────────────


async def save_pv(pv: dict[str, Any]) -> str:
    """Persist a PV (with its actions/todos) into the fallback store.

    Returns the pv_id.
    """
    pv_id: str = pv.get("pv_id", "")
    if not pv_id:
        logger.error("Cannot save PV without pv_id")
        return ""

    async with _lock:
        store = _read_store()
        store[pv_id] = {
            "pv": pv,
            "stored_at": datetime.utcnow().isoformat(),
            "routed_to": "fallback (ora_studio unavailable)",
        }
        _write_store(store)

    logger.info("PV %s saved to fallback store (%d tasks)", pv_id, len(pv.get("actions", [])))
    return pv_id


async def list_pvs(
    call_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List all stored PVs, optionally filtered by call_type.

    Returns a lightweight list (no full compte_rendu) for the overview.
    """
    store = _read_store()
    result = []
    for pv_id, entry in store.items():
        pv = entry.get("pv", {})
        if call_type and pv.get("call_type") != call_type:
            continue
        result.append(
            {
                "pv_id": pv_id,
                "call_date": pv.get("call_date"),
                "call_type": pv.get("call_type"),
                "subject": pv.get("subject"),
                "left": pv.get("left", {}).get("name"),
                "right": pv.get("right", {}).get("name"),
                "additional_participants": [
                    p.get("name")
                    for p in pv.get("additional_participants", [])
                    if isinstance(p, dict)
                ],
                "task_count": len(pv.get("actions", [])),
                "meeting_created": pv.get("meeting_created", False),
                "stored_at": entry.get("stored_at"),
            }
        )
    # Newest first
    result.sort(key=lambda r: r.get("stored_at", ""), reverse=True)
    return result[:limit]


async def get_pv(pv_id: str) -> dict[str, Any] | None:
    """Retrieve a full PV by its id."""
    store = _read_store()
    entry = store.get(pv_id)
    if entry is None:
        return None
    return entry["pv"]


async def get_todos(pv_id: str | None = None) -> list[dict[str, Any]]:
    """Get todo items.

    If pv_id is provided, returns todos for that specific PV.
    Otherwise returns all todos across all PVs.
    """
    store = _read_store()
    all_todos: list[dict[str, Any]] = []

    for sid, entry in store.items():
        if pv_id and sid != pv_id:
            continue
        pv = entry.get("pv", {})
        for task in pv.get("actions", []):
            all_todos.append(
                {
                    "pv_id": sid,
                    "pv_subject": pv.get("subject"),
                    "call_date": pv.get("call_date"),
                    "title": task.get("title"),
                    "owner": task.get("owner"),
                    "deadline": task.get("deadline"),
                    "difficulty": task.get("difficulty"),
                    "model_hint": task.get("model_hint"),
                }
            )

    # Sort by deadline (ascending), None at bottom
    all_todos.sort(key=lambda t: (t.get("deadline") is None, t.get("deadline", "")))
    return all_todos


async def clear_store() -> int:
    """Remove all entries. Returns count of removed items."""
    async with _lock:
        store = _read_store()
        count = len(store)
        _write_store({})
    logger.info("Fallback store cleared: %d PVs removed", count)
    return count
