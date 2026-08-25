"""CRM Vocal — FastAPI application entry point.

Phase 1: Test endpoints for the AI pipeline.
Phase 2: WebSocket endpoint for live calls.
"""

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.agent.summarizer import summarize
from app.agent.classifier import classify
from app.agent.action_extractor import extract
from app.routing.router import route
from app.models.call import CallStartRequest
from app.config import settings
from app.ws.call_handler import member_handler
from app import fallback_store

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crm-vocal")

app = FastAPI(
    title="CRM Vocal",
    description="Ora Telecom — AI-powered call analysis pipeline",
    version="0.1.0",
)

# CORS — allow the test UI from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── UI ───────────────────────────────────────────────────────────────

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the test UI."""
    index_path = UI_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


# Serve the rest of the ui/ folder (call.html, call.js, pcm-worklet.js, …).
# getUserMedia requires a secure context (localhost/https), so the calling page
# must be reachable over HTTP rather than opened as file://.
app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


# ── API ──────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "deepseek_configured": bool(settings.deepseek_api_key),
    }


@app.post("/api/call/start")
async def call_start(request: CallStartRequest):
    """Start a new call session. Returns the session_id.

    In Phase 1, this just validates and returns the session info.
    The actual pipeline runs via POST /api/call/process.
    """
    logger.info("Call session created: %s", request.session_id)
    return {
        "session_id": request.session_id,
        "status": "created",
        "left": request.left.model_dump(),
        "right": request.right.model_dump(),
        "subject": request.subject,
    }


@app.post("/api/call/session")
async def create_call_session(request: dict):
    """Create (or fetch) a call session id. Returns the ``session_id``.

    Lightweight — the multi-member WebSocket handler also auto-creates the
    session on first member attach, so this just reserves an id up front (e.g.
    so the lobby can build invite links before anyone joins).
    """
    session_id = (request.get("session_id") or "").strip() or str(uuid.uuid4())
    return {
        "session_id": session_id,
        "join_path": f"/ws/call/{session_id}/{{speaker_id}}",
    }


@app.post("/api/call/process")
async def call_process(request: dict):
    """Process a transcript through the full AI pipeline.

    Expects:
    {
        "transcript": "full call transcript text...",
        "session_id": "optional-session-id",
        "call_date": "2026-06-19T14:00:00Z"  // optional
    }

    Returns the complete PV with routing results.
    """
    transcript = request.get("transcript", "")
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript is required")

    call_date = request.get("call_date")
    session_id = request.get("session_id", "unknown")

    logger.info("Processing call %s — %d chars", session_id, len(transcript))

    try:
        # Step 1: Summarize
        pv = await summarize(transcript, call_date=call_date)

        # Step 2: Validate call type (LLM already classified — just sanity-check)
        pv["call_type"] = classify(pv.get("call_type"))

        # Step 3: Extract actions
        actions = extract(pv)
        pv["actions"] = actions

        # Step 4: Route
        routing_result = await route(pv)

        return {
            "session_id": session_id,
            "pv": pv,
            "routing": routing_result,
        }
    except Exception as e:
        logger.exception("Pipeline failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket: multi-member real-time call (Phase 2) ─────────────────────


@app.websocket("/ws/call/{session_id}/{speaker_id}")
async def ws_member(
    websocket: WebSocket,
    session_id: str,
    speaker_id: str,
    side: str | None = None,
    role: str | None = None,
    phone: str | None = None,
):
    """One WebSocket per member. Each member streams its own mic audio.

    ``speaker_id`` is the member's declared identity (e.g. "Sami", "Lina").
    Optional query params let the client declare caller intel up front (the
    lobby already collected it), so the summarizer assigns participants
    deterministically and the PV carries the real phone + job title:
      ws://host/ws/call/{session_id}/{speaker_id}?side=right&role=CEO&phone=%2B216...
    """
    await member_handler(
        websocket, session_id, speaker_id, side=side, role=role, phone=phone
    )


# ── Fallback UI API (Next.js consumes these) ────────────────────────────


@app.get("/api/fallback/pvs")
async def list_fallback_pvs(
    call_type: str | None = Query(default=None, description="Filter by call_type"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List all PVs stored in the fallback store (lightweight overview)."""
    pvs = await fallback_store.list_pvs(call_type=call_type, limit=limit)
    return {"count": len(pvs), "pvs": pvs}


@app.get("/api/fallback/pvs/{pv_id}")
async def get_fallback_pv(pv_id: str):
    """Retrieve a full PV by its ID."""
    pv = await fallback_store.get_pv(pv_id)
    if pv is None:
        raise HTTPException(status_code=404, detail=f"PV {pv_id} not found")
    return pv


@app.get("/api/fallback/todos")
async def list_fallback_todos(
    pv_id: str | None = Query(default=None, description="Filter by PV ID"),
):
    """List all todo items, optionally filtered by PV."""
    todos = await fallback_store.get_todos(pv_id=pv_id)
    return {"count": len(todos), "todos": todos}


@app.delete("/api/fallback/pvs")
async def clear_fallback_store():
    """Admin: clear the entire fallback store."""
    removed = await fallback_store.clear_store()
    return {"status": "cleared", "removed": removed}
