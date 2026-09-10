"""Domain models aligned with MCP tool contract v1.3."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Literal


class SpeakCategory(str, Enum):
    progress = "progress"
    error = "error"
    decision = "decision"
    summary = "summary"


class SpeakPriority(str, Enum):
    normal = "normal"
    high = "high"


class SpeakCode(str, Enum):
    OK = "OK"
    DISABLED = "DISABLED"
    INVALID_TEXT = "INVALID_TEXT"
    TEXT_TOO_LONG = "TEXT_TOO_LONG"
    DEDUPED = "DEDUPED"
    ENGINE_FAILED = "ENGINE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StopCode(str, Enum):
    OK = "OK"
    NOT_PLAYING = "NOT_PLAYING"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class SpeakRequest:
    text: str
    priority: SpeakPriority = SpeakPriority.normal
    category: SpeakCategory = SpeakCategory.progress
    interrupt: bool = False
    interrupt_explicit: bool = False  # True if caller passed interrupt


@dataclass
class SpeakResult:
    ok: bool
    code: str
    queued: bool
    message: str
    engine: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "engine": self.engine,
            "queued": self.queued,
            "message": self.message,
        }


@dataclass
class StopResult:
    ok: bool
    code: str
    was_playing: bool
    cleared: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EngineName = Literal["edge-tts", "sapi"]
