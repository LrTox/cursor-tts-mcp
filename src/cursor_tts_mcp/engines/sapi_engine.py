"""Windows SAPI engine — delegates speaking to killable Player."""

from __future__ import annotations

import logging

from cursor_tts_mcp.engines.base import EngineOutcome
from cursor_tts_mcp.playback.player import Player

logger = logging.getLogger("cursor_tts_mcp.engines.sapi")


class SapiEngine:
    name = "sapi"

    def __init__(self, player: Player) -> None:
        self._player = player

    async def synthesize(
        self, text: str, *, voice: str, rate: str
    ) -> EngineOutcome:
        # rate unused for SAPI in P0
        _ = rate
        logger.info("engine=sapi synthesizing chars=%s", len(text))
        await self._player.speak_sapi(text, voice=voice)
        return EngineOutcome(mode="direct", engine=self.name)
