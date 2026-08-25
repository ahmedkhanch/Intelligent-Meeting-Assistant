"""TaskItem — shared task schema used across the pipeline."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class TaskItem(BaseModel):
    """A single action item or todo extracted from a call.

    For commercial calls: title + owner + deadline (difficulty is None).
    For tech calls: title + owner + deadline + difficulty + model_hint.
    """

    title: str
    owner: str
    deadline: date | None = None
    difficulty: Literal["facile", "difficile", "très difficile"] | None = None
    model_hint: (
        Literal["gpt-4o-mini", "claude-sonnet-4-6", "claude-opus-4-6"] | None
    ) = None

    @property
    def resolve_model(self) -> str:
        """Map difficulty to the model Ora Studio should use for this task."""
        return {
            "facile": "gpt-4o-mini",
            "difficile": "claude-sonnet-4-6",
            "très difficile": "claude-opus-4-6",
        }.get(self.difficulty or "", "claude-sonnet-4-6")
