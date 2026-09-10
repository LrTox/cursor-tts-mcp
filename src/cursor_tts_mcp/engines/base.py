"""TTS engine protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class EngineOutcome:
    mode: Literal["direct", "file"]
    path: str | None = None
    engine: str = ""


class TtsEngine(Protocol):
    name: str

    async def synthesize(
        self, text: str, *, voice: str, rate: str
    ) -> EngineOutcome:
        """Produce file path or signal direct playback already done."""
        ...
