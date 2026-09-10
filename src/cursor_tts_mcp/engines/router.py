"""Primary → fallback engine router."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from cursor_tts_mcp.config import TtsSettings
from cursor_tts_mcp.engines.base import EngineOutcome, TtsEngine
from cursor_tts_mcp.engines.edge_tts_engine import EdgeTtsEngine
from cursor_tts_mcp.engines.sapi_engine import SapiEngine
from cursor_tts_mcp.logging_util import log_event
from cursor_tts_mcp.playback.player import Player

logger = logging.getLogger("cursor_tts_mcp.engines.router")


class EngineRouter:
    def __init__(self, settings: TtsSettings, player: Player) -> None:
        self._settings = settings
        self._player = player
        self._edge = EdgeTtsEngine(timeout_ms=settings.edge.timeout_ms)
        self._sapi = SapiEngine(player)

    def _primary(self) -> TtsEngine:
        if self._settings.engine.primary == "sapi":
            if not self._settings.engine.allow_sapi:
                raise RuntimeError(
                    "SAPI disabled (mechanical voice). "
                    "Use edge-tts, or set CURSOR_TTS_ALLOW_SAPI=true only if needed."
                )
            return self._sapi
        return self._edge

    def _fallback(self) -> TtsEngine | None:
        if not self._settings.engine.fallback_enabled:
            return None
        if self._settings.engine.fallback == "sapi":
            if not self._settings.engine.allow_sapi:
                log_event(
                    logger,
                    logging.WARNING,
                    "sapi_blocked",
                    reason="allow_sapi=false; skip mechanical fallback",
                )
                return None
            return self._sapi
        if self._settings.engine.fallback == "edge-tts":
            return self._edge
        return None

    async def speak(self, text: str) -> EngineOutcome:
        settings = self._settings
        primary = self._primary()
        timeout = settings.edge.timeout_ms / 1000.0
        voice = (
            settings.edge.voice
            if primary.name == "edge-tts"
            else settings.sapi.voice
        )
        rate = settings.rate

        try:
            if primary.name == "edge-tts":
                outcome = await asyncio.wait_for(
                    primary.synthesize(text, voice=voice, rate=rate),
                    timeout=timeout,
                )
            else:
                outcome = await primary.synthesize(text, voice=voice, rate=rate)
            await self._play_outcome(outcome)
            engine_name = outcome.engine or primary.name
            log_event(
                logger,
                logging.INFO,
                "engine_ok",
                engine=engine_name,
                fallback=False,
            )
            return outcome
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "engine_failed",
                engine=primary.name,
                reason=str(exc),
            )
            fb = self._fallback()
            if fb is None or fb.name == primary.name:
                raise
            fb_voice = (
                settings.edge.voice
                if fb.name == "edge-tts"
                else settings.sapi.voice
            )
            outcome = await fb.synthesize(text, voice=fb_voice, rate=rate)
            await self._play_outcome(outcome)
            engine_name = outcome.engine or fb.name
            log_event(
                logger,
                logging.INFO,
                "engine_ok",
                engine=engine_name,
                fallback=True,
                reason=f"primary {primary.name} failed",
            )
            return outcome

    async def _play_outcome(self, outcome: EngineOutcome) -> None:
        if outcome.mode == "file" and outcome.path:
            try:
                await self._player.play_file(outcome.path)
            finally:
                try:
                    Path(outcome.path).unlink(missing_ok=True)
                except Exception:
                    logger.debug("temp cleanup failed", exc_info=True)
