"""Text validation and normalize (contract §3.4 / §3.6)."""

from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """trim + collapse whitespace; no case folding."""
    return _WS_RE.sub(" ", text.strip())


def validate_speak_text(
    text: str, *, max_chars: int
) -> tuple[str | None, str | None]:
    """
    Returns (cleaned_text, error_code).
    error_code is INVALID_TEXT | TEXT_TOO_LONG | None.
    """
    trimmed = text.strip()
    if not trimmed:
        return None, "INVALID_TEXT"
    if len(trimmed) > max_chars:
        return None, "TEXT_TOO_LONG"
    return trimmed, None
