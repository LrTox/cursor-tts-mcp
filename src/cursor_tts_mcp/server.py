"""MCP stdio server for cursor-tts (thin client in http mode)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer

from cursor_tts_mcp.client import TtsHttpClient
from cursor_tts_mcp.config import TtsSettings, _repo_root, load_settings, setup_logging
from cursor_tts_mcp.core.orchestrator import Orchestrator
from cursor_tts_mcp.tools import (
    STOP_DESCRIPTION,
    build_speak_description,
    handle_speak,
    handle_stop,
)

logger = logging.getLogger("cursor_tts_mcp.server")

_backend: Orchestrator | TtsHttpClient | None = None
_settings: TtsSettings | None = None
_service_proc: subprocess.Popen[Any] | None = None
_init_error: str | None = None
_autostart_log_f: Any | None = None


def _wait_healthy(url: str, attempts: int = 30, delay_s: float = 0.2) -> bool:
    for _ in range(attempts):
        try:
            r = httpx.get(f"{url.rstrip('/')}/v1/health", timeout=0.5)
            if r.status_code == 200 and r.json().get("ok"):
                return True
        except Exception:
            pass
        time.sleep(delay_s)
    return False


def _ensure_service(settings: TtsSettings) -> None:
    global _service_proc, _autostart_log_f
    url = settings.service.url
    if _wait_healthy(url, attempts=3, delay_s=0.1):
        logger.info("tts_service already healthy at %s", url)
        return
    if not settings.service.autostart:
        raise RuntimeError(
            f"tts_service not reachable at {url} and autostart disabled"
        )
    # Previous child may have died; start a fresh one.
    if _service_proc is not None and _service_proc.poll() is not None:
        _service_proc = None
    logger.info("autostarting tts_service for %s via %s", url, sys.executable)
    log_path = _repo_root() / ".cursor" / "tts_service.autostart.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if _autostart_log_f is None:
        _autostart_log_f = open(log_path, "a", encoding="utf-8")
    _service_proc = subprocess.Popen(
        [sys.executable, "-m", "tts_service"],
        cwd=str(_repo_root()),
        stdout=subprocess.DEVNULL,
        stderr=_autostart_log_f,
        env={**os.environ},
    )
    if not _wait_healthy(url, attempts=50, delay_s=0.2):
        raise RuntimeError(
            f"tts_service failed to become healthy at {url} "
            f"(pid={_service_proc.pid if _service_proc else None}; "
            f"see {log_path})"
        )
    logger.info(
        "tts_service autostart healthy pid=%s",
        _service_proc.pid if _service_proc else None,
    )


def reset_backend() -> None:
    """Drop cached backend so the next get_backend() can re-autostart."""
    global _backend, _init_error
    _backend = None
    _init_error = None


def get_backend() -> Orchestrator | TtsHttpClient:
    """Lazy init — must NOT run before MCP stdio handshake."""
    global _backend, _settings, _init_error
    if _backend is not None:
        return _backend
    if _init_error:
        raise RuntimeError(_init_error)
    settings = load_settings()
    setup_logging(settings.log_level)
    _settings = settings
    mode = settings.service.mode.lower()
    try:
        if mode == "embedded":
            _backend = Orchestrator(settings)
            logger.info(
                "cursor-tts embedded mode primary=%s",
                settings.engine.primary,
            )
        else:
            _ensure_service(settings)
            _backend = TtsHttpClient(settings.service.url)
            logger.info("cursor-tts http mode url=%s", settings.service.url)
    except Exception as exc:
        _init_error = str(exc)
        logger.exception("backend init failed")
        raise
    return _backend


async def get_backend_ready() -> Orchestrator | TtsHttpClient:
    """Return backend; if HTTP service died, re-autostart once."""
    backend = get_backend()
    if not isinstance(backend, TtsHttpClient):
        return backend
    if await backend.health():
        return backend
    logger.warning("tts_service unhealthy; resetting backend and re-autostarting")
    reset_backend()
    return get_backend()


def create_app() -> MCPServer:
    settings = load_settings()
    speak_description = build_speak_description(
        language=settings.resolved_language,
        speak_hint=settings.speak_hint,
    )
    server = MCPServer("cursor-tts")

    @server.tool(name="speak", description=speak_description)
    async def speak(
        text: str,
        priority: Literal["normal", "high"] = "normal",
        category: Literal["progress", "error", "decision", "summary"] = "progress",
        interrupt: bool | None = None,
    ) -> str:
        """Speak a short status line in the system UI language."""
        args: dict[str, Any] = {
            "text": text,
            "priority": priority,
            "category": category,
        }
        if interrupt is not None:
            args["interrupt"] = interrupt
        try:
            result = await handle_speak(await get_backend_ready(), args)
            body = result["content"][0]["text"]
            if "tts service unavailable" in body or "backend unavailable" in body:
                logger.warning("speak failed with service down; retry after re-autostart")
                reset_backend()
                result = await handle_speak(await get_backend_ready(), args)
                body = result["content"][0]["text"]
            return body
        except Exception:
            import json

            try:
                reset_backend()
                result = await handle_speak(await get_backend_ready(), args)
                return result["content"][0]["text"]
            except Exception as exc2:
                return json.dumps(
                    {
                        "ok": False,
                        "code": "INTERNAL_ERROR",
                        "engine": None,
                        "queued": False,
                        "message": f"backend unavailable: {exc2}",
                    },
                    ensure_ascii=False,
                )

    @server.tool(name="stop", description=STOP_DESCRIPTION)
    async def stop(clear_queue: bool = True) -> str:
        """立即停止当前语音播报。"""
        try:
            result = await handle_stop(await get_backend_ready(), {"clear_queue": clear_queue})
            return result["content"][0]["text"]
        except Exception:
            import json

            try:
                reset_backend()
                result = await handle_stop(
                    await get_backend_ready(), {"clear_queue": clear_queue}
                )
                return result["content"][0]["text"]
            except Exception as exc2:
                return json.dumps(
                    {
                        "ok": False,
                        "code": "INTERNAL_ERROR",
                        "was_playing": False,
                        "cleared": False,
                        "message": f"backend unavailable: {exc2}",
                    },
                    ensure_ascii=False,
                )

    return server


async def run() -> None:
    # Load settings/logging only — do NOT block on HTTP service before handshake.
    settings = load_settings()
    setup_logging(settings.log_level)
    logger.info(
        "cursor-tts MCP starting mode=%s url=%s",
        settings.service.mode,
        settings.service.url,
    )
    server = create_app()
    await server.run_stdio_async()
