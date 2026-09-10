"""edge-tts engine — write MP3 then play via Player."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

import edge_tts

from cursor_tts_mcp.engines.base import EngineOutcome

logger = logging.getLogger("cursor_tts_mcp.engines.edge")


class EdgeTtsEngine:
    name = "edge-tts"

    def __init__(self, timeout_ms: int = 8000) -> None:
        self._timeout_ms = timeout_ms

    async def synthesize(
        self, text: str, *, voice: str, rate: str
    ) -> EngineOutcome:
        tmp_dir = Path(tempfile.gettempdir()) / "cursor-tts-mcp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        out = tmp_dir / f"{uuid.uuid4().hex}.mp3"
        logger.info("engine=edge-tts synthesizing voice=%s path=%s", voice, out)
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        # edge-tts save; wrap with timeout at router level preferably
        await communicate.save(str(out))
        return EngineOutcome(mode="file", path=str(out), engine=self.name)
