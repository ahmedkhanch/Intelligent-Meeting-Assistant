"""Classifier — validates call_type from the LLM summarizer.

As of Phase 1, call type classification is done entirely by DeepSeek
during summarization. The LLM understands context — keyword scoring was
removed because it can't disambiguate commercial calls that mention tech
terms (or vice versa).

This module now serves as a thin validation layer:
- Passes through valid call_type values from the LLM
- Defaults to #appel-commercial if the LLM returns something invalid
"""

import logging
from typing import Literal

logger = logging.getLogger(__name__)

CallType = Literal["#appel-commercial", "#appel-tech"]

VALID_CALL_TYPES: set[str] = {"#appel-commercial", "#appel-tech"}


def validate(call_type: str | None) -> CallType:
    """Validate the call_type returned by the LLM summarizer.

    The summarizer prompt instructs DeepSeek to auto-detect the call type
    from context. This function acts as a safety net — it passes through
    valid values and defaults sensibly when the LLM output is malformed.

    Returns:
        "#appel-commercial" or "#appel-tech"
    """
    if call_type and call_type.strip() in VALID_CALL_TYPES:
        logger.info("Call type validated: %s", call_type)
        return call_type.strip()  # type: ignore[return-value]

    logger.warning(
        "LLM returned invalid call_type=%r — defaulting to #appel-commercial",
        call_type,
    )
    return "#appel-commercial"


# ── Backward compatibility alias (used by scripts that imported classify) ──

classify = validate
