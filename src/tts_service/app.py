"""HTTP API for TTS: /v1/speak, /v1/stop, /v1/health."""

from __future__ import annotations

import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from cursor_tts_mcp.config import load_settings, setup_logging
from cursor_tts_mcp.core.orchestrator import Orchestrator
from cursor_tts_mcp.models import SpeakCategory, SpeakPriority, SpeakRequest

logger = logging.getLogger("cursor_tts_mcp.tts_service")

_orch: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orch
    if _orch is None:
        settings = load_settings()
        setup_logging(settings.log_level)
        _orch = Orchestrator(settings)
        logger.info(
            "tts_service orchestrator ready primary=%s locale=%s voice=%s",
            settings.engine.primary,
            settings.resolved_locale,
            settings.edge.voice,
        )
    return _orch


async def health(_: Request) -> JSONResponse:
    orch = get_orchestrator()
    s = orch.settings
    return JSONResponse(
        {
            "ok": True,
            "service": "tts_service",
            "version": "0.1.0",
            "locale": s.resolved_locale,
            "language": s.resolved_language,
            "locale_source": s.resolved_locale_source,
            "edge_voice": s.edge.voice,
            "speak_hint": s.speak_hint,
        }
    )


async def speak(request: Request) -> JSONResponse:
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(
            {
                "ok": False,
                "code": "INTERNAL_ERROR",
                "engine": None,
                "queued": False,
                "message": "invalid json body",
            },
            status_code=400,
        )

    text = body.get("text", "")
    if not isinstance(text, str):
        text = str(text)
    priority_raw = body.get("priority", "normal")
    category_raw = body.get("category", "progress")
    interrupt_explicit = "interrupt" in body
    interrupt = bool(body.get("interrupt", False))

    try:
        priority = SpeakPriority(priority_raw)
    except ValueError:
        priority = SpeakPriority.normal
    try:
        category = SpeakCategory(category_raw)
    except ValueError:
        return JSONResponse(
            {
                "ok": False,
                "code": "INTERNAL_ERROR",
                "engine": None,
                "queued": False,
                "message": f"invalid category: {category_raw}",
            },
            status_code=400,
        )

    req = SpeakRequest(
        text=text,
        priority=priority,
        category=category,
        interrupt=interrupt,
        interrupt_explicit=interrupt_explicit,
    )
    result = await get_orchestrator().speak(req)
    return JSONResponse(result.to_dict())


async def stop(request: Request) -> JSONResponse:
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}
    clear_queue = bool(body.get("clear_queue", True))
    result = await get_orchestrator().stop(clear_queue=clear_queue)
    return JSONResponse(result.to_dict())


def create_app() -> Starlette:
    # touch orchestrator at import/startup for faster first speak
    get_orchestrator()
    return Starlette(
        routes=[
            Route("/v1/health", health, methods=["GET"]),
            Route("/v1/speak", speak, methods=["POST"]),
            Route("/v1/stop", stop, methods=["POST"]),
        ]
    )
