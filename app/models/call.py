"""Call session schema."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.pv import PV, Participant


class CallStartRequest(BaseModel):
    """Payload sent by the test UI (or production trigger) to start a call."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    left: Participant
    right: Participant
    additional_participants: list[Participant] = Field(default_factory=list)
    subject: str


class CallSession(BaseModel):
    """Internal representation of an active call."""

    session_id: str
    state: Literal["waiting", "in_progress", "summarizing", "done", "error"] = (
        "waiting"
    )
    started_at: datetime | None = None
    ended_at: datetime | None = None
    transcript: str = ""
    pv: PV | None = None
    left: Participant | None = None
    right: Participant | None = None
    additional_participants: list[Participant] = Field(default_factory=list)
    subject: str = ""
    call_type: str = ""  # filled after classification
    error: str | None = None
