"""Speak/stop orchestrator: accept-and-return, queue, interrupt, dedupe."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from cursor_tts_mcp.config import TtsSettings
from cursor_tts_mcp.core.text_policy import normalize_text, validate_speak_text
from cursor_tts_mcp.engines.router import EngineRouter
from cursor_tts_mcp.logging_util import log_event
from cursor_tts_mcp.models import (
    SpeakCategory,
    SpeakCode,
    SpeakRequest,
    SpeakResult,
    StopCode,
    StopResult,
)
from cursor_tts_mcp.playback.player import Player

logger = logging.getLogger("cursor_tts_mcp.orchestrator")


class Orchestrator:
    def __init__(self, settings: TtsSettings) -> None:
        self.settings = settings
        self.player = Player(exclusive=settings.playback.exclusive)
        self.router = EngineRouter(settings, self.player)
        self._lock = asyncio.Lock()
        self._queue: deque[SpeakRequest] = deque()
        self._worker: asyncio.Task[None] | None = None
        self._current: SpeakRequest | None = None
        self._dedupe: dict[str, float] = {}

    async def speak(self, req: SpeakRequest) -> SpeakResult:
        if not self.settings.enabled:
            log_event(
                logger,
                logging.INFO,
                "speak_reject",
                category=req.category.value,
                code=SpeakCode.DISABLED.value,
                reason="tts disabled",
            )
            return SpeakResult(
                ok=False,
                code=SpeakCode.DISABLED.value,
                engine=None,
                queued=False,
                message="tts disabled",
            )

        cleaned, err = validate_speak_text(
            req.text, max_chars=self.settings.max_chars
        )
        if err:
            log_event(
                logger,
                logging.INFO,
                "speak_reject",
                category=req.category.value,
                code=err,
                reason=err,
                text=req.text[:40],
            )
            return SpeakResult(
                ok=False,
                code=err,
                engine=None,
                queued=False,
                message=(
                    "empty text"
                    if err == SpeakCode.INVALID_TEXT.value
                    else f"text exceeds max_chars={self.settings.max_chars}"
                ),
            )
        assert cleaned is not None
        req.text = cleaned

        # error category defaults interrupt=true when not explicit
        if (
            req.category == SpeakCategory.error
            and not req.interrupt_explicit
        ):
            req.interrupt = True

        dedupe_key = f"{normalize_text(req.text)}\0{req.category.value}"
        window = self.settings.dedupe_window_ms / 1000.0

        async with self._lock:
            now = time.monotonic()
            self._dedupe = {
                k: t for k, t in self._dedupe.items() if now - t <= window
            }
            if (
                dedupe_key in self._dedupe
                and now - self._dedupe[dedupe_key] <= window
            ):
                log_event(
                    logger,
                    logging.INFO,
                    "speak_deduped",
                    category=req.category.value,
                    code=SpeakCode.DEDUPED.value,
                    text=req.text[:40],
                )
                return SpeakResult(
                    ok=True,
                    code=SpeakCode.DEDUPED.value,
                    engine=None,
                    queued=False,
                    message="duplicate within dedupe window",
                )
            self._dedupe[dedupe_key] = now

            if req.interrupt:
                await self.player.stop()
                self._queue.clear()
                self._current = None
                # cancel worker so we reschedule
                if self._worker and not self._worker.done():
                    self._worker.cancel()
                    self._worker = None

            playing = self.player.is_playing or self._current is not None
            if playing and not req.interrupt:
                # enqueue
                while len(self._queue) >= self.settings.queue_size:
                    dropped = self._queue.popleft()
                    log_event(
                        logger,
                        logging.INFO,
                        "queue_overflow_drop",
                        category=dropped.category.value,
                        text=dropped.text[:40],
                    )
                self._queue.append(req)
                queued = True
            else:
                self._queue.appendleft(req)
                queued = False

            self._ensure_worker()

        log_event(
            logger,
            logging.INFO,
            "speak_accepted",
            category=req.category.value,
            code=SpeakCode.OK.value,
            interrupt=req.interrupt,
            queued=queued,
            text=req.text[:40],
        )
        return SpeakResult(
            ok=True,
            code=SpeakCode.OK.value,
            engine=None,
            queued=queued,
            message="accepted",
        )

    async def stop(self, *, clear_queue: bool = True) -> StopResult:
        async with self._lock:
            was = self.player.is_playing or self._current is not None
            await self.player.stop()
            cleared = False
            if clear_queue:
                self._queue.clear()
                cleared = True
            self._current = None
            if self._worker and not self._worker.done():
                self._worker.cancel()
                self._worker = None

        if not was:
            log_event(
                logger,
                logging.INFO,
                "stop",
                code=StopCode.NOT_PLAYING.value,
                was_playing=False,
                cleared=cleared,
            )
            return StopResult(
                ok=True,
                code=StopCode.NOT_PLAYING.value,
                was_playing=False,
                cleared=cleared,
                message="nothing playing",
            )
        log_event(
            logger,
            logging.INFO,
            "stop",
            code=StopCode.OK.value,
            was_playing=True,
            cleared=cleared,
        )
        return StopResult(
            ok=True,
            code=StopCode.OK.value,
            was_playing=True,
            cleared=cleared,
            message="stopped",
        )

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_queue())

    async def _run_queue(self) -> None:
        try:
            while True:
                async with self._lock:
                    if not self._queue:
                        self._current = None
                        self._worker = None
                        return
                    req = self._queue.popleft()
                    self._current = req
                try:
                    outcome = await self.router.speak(req.text)
                    log_event(
                        logger,
                        logging.INFO,
                        "speak_played",
                        category=req.category.value,
                        engine=outcome.engine,
                        text=req.text[:40],
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_event(
                        logger,
                        logging.ERROR,
                        "speak_failed",
                        category=req.category.value,
                        engine=None,
                        reason=str(exc),
                        text=req.text[:40],
                    )
                    logger.exception("background speak failed")
                finally:
                    async with self._lock:
                        self._current = None
        except asyncio.CancelledError:
            logger.info("queue worker cancelled")
            raise
