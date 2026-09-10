"""Structured stderr log helpers for AC-P1-04."""

from __future__ import annotations

import logging
from typing import Any


def fmt_fields(**fields: Any) -> str:
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, str):
            text = value.replace("\n", " ").replace("\r", "")
            if len(text) > 80:
                text = text[:80] + "…"
            parts.append(f"{key}={text!r}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, "%s %s", event, fmt_fields(**fields))
