"""Action extractor — pulls structured tasks from the PV and enriches them.

For commercial calls: validates action items with owner + deadline.
For tech calls: validates todos with owner + deadline + difficulty + model_hint.
"""

import logging
from datetime import date

from app.models.task import TaskItem

logger = logging.getLogger(__name__)


def extract(pv: dict) -> list[dict]:
    """Extract and validate action items from PV JSON.

    Returns a list of validated TaskItem dicts, enriched with model_hint
    for tech calls.
    """
    call_type = pv.get("call_type", "#appel-commercial")
    raw_actions = pv.get("actions", [])

    validated = []
    for i, action in enumerate(raw_actions):
        try:
            task = _validate_and_enrich(action, call_type, i)
            validated.append(task)
        except ValueError as e:
            logger.warning("Skipping invalid action #%d: %s", i, e)

    logger.info("Extracted %d/%d valid actions for %s", len(validated), len(raw_actions), call_type)
    return validated


def _validate_and_enrich(action: dict, call_type: str, index: int) -> dict:
    """Validate a single action and enrich with model_hint for tech calls."""
    title = (action.get("title") or "").strip()
    if not title:
        raise ValueError(f"Action #{index} has no title")

    owner = (action.get("owner") or "").strip()
    if not owner:
        raise ValueError(f"Action '{title}' has no owner")

    # Parse deadline
    deadline = action.get("deadline")
    if deadline and isinstance(deadline, str):
        try:
            deadline = date.fromisoformat(deadline)
        except ValueError:
            deadline = None

    # Difficulty — only for tech calls
    difficulty = None
    model_hint = None
    if call_type == "#appel-tech":
        difficulty = action.get("difficulty")
        if difficulty not in ("facile", "difficile", "très difficile"):
            difficulty = "difficile"  # sensible default
        model_hint = _resolve_model_hint(difficulty)

    task = TaskItem(
        title=title,
        owner=owner,
        deadline=deadline if deadline else None,
        difficulty=difficulty,
        model_hint=model_hint,
    )

    return task.model_dump(mode="json")


def _resolve_model_hint(difficulty: str) -> str:
    """Map difficulty to the model Ora Studio should use."""
    return {
        "facile": "gpt-4o-mini",
        "difficile": "claude-sonnet-4-6",
        "très difficile": "claude-opus-4-6",
    }.get(difficulty, "claude-sonnet-4-6")
