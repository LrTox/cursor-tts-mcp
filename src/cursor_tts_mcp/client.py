"""HTTP client to local tts_service (MCP thin adapter)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from cursor_tts_mcp.models import SpeakRequest, SpeakResult, StopResult

logger = logging.getLogger("cursor_tts_mcp.client")


class TtsHttpClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                r = await client.get(f"{self.base_url}/v1/health")
                return r.status_code == 200 and bool(r.json().get("ok"))
        except Exception as exc:
            logger.warning("health check failed: %s", exc)
            return False

    async def speak(self, req: SpeakRequest) -> SpeakResult:
        payload: dict[str, Any] = {
            "text": req.text,
            "priority": req.priority.value,
            "category": req.category.value,
        }
        if req.interrupt_explicit:
            payload["interrupt"] = req.interrupt
        elif req.interrupt:
            payload["interrupt"] = True
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                r = await client.post(f"{self.base_url}/v1/speak", json=payload)
                data = r.json()
        except Exception as exc:
            logger.error("speak http failed: %s", exc)
            return SpeakResult(
                ok=False,
                code="INTERNAL_ERROR",
                engine=None,
                queued=False,
                message=f"tts service unavailable: {exc}",
            )
        return SpeakResult(
            ok=bool(data.get("ok")),
            code=str(data.get("code", "INTERNAL_ERROR")),
            engine=data.get("engine"),
            queued=bool(data.get("queued", False)),
            message=str(data.get("message", "")),
        )

    async def stop(self, *, clear_queue: bool = True) -> StopResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                r = await client.post(
                    f"{self.base_url}/v1/stop",
                    json={"clear_queue": clear_queue},
                )
                data = r.json()
        except Exception as exc:
            logger.error("stop http failed: %s", exc)
            return StopResult(
                ok=False,
                code="INTERNAL_ERROR",
                was_playing=False,
                cleared=False,
                message=f"tts service unavailable: {exc}",
            )
        return StopResult(
            ok=bool(data.get("ok")),
            code=str(data.get("code", "INTERNAL_ERROR")),
            was_playing=bool(data.get("was_playing", False)),
            cleared=bool(data.get("cleared", False)),
            message=str(data.get("message", "")),
        )
