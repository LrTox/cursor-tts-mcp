"""MCP tool handlers — local orchestrator or HTTP client backend."""

from __future__ import annotations

import json
from typing import Any, Protocol

from cursor_tts_mcp.models import SpeakCategory, SpeakPriority, SpeakRequest, SpeakResult, StopResult

_SPEAK_DESCRIPTION_BASE = (
    "Speak a short status line for important mid-process content — not only start/end. "
    "Speak findings, conclusions, diffs, root causes, verified facts, risks, and verification "
    "results as soon as they appear (including during Plan subtasks). Multiple speaks per turn. "
    "Also speak for errors/blocks and when the user must decide. "
    "Do not speak on every trivial tool success. Do not read code, long text, or full plans."
)

STOP_DESCRIPTION = (
    "Immediately stop current TTS playback. "
    "Default clear_queue=true; if false, only stop current and keep the queue."
)


def build_speak_description(*, language: str = "zh", speak_hint: str = "简体中文短句") -> str:
    """Tool description that asks the agent to match OS UI language."""
    return (
        f"{_SPEAK_DESCRIPTION_BASE} "
        f"Speak in the system UI language ({language}): use {speak_hint} "
        f"(≤80 characters). Do not force Chinese if the system language is not Chinese."
    )


# Default at import; server refreshes from load_settings().
SPEAK_DESCRIPTION = build_speak_description()


class SpeakBackend(Protocol):
    async def speak(self, req: SpeakRequest) -> SpeakResult: ...

    async def stop(self, *, clear_queue: bool = True) -> StopResult: ...


def _json_content(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]


async def handle_speak(backend: SpeakBackend, arguments: dict[str, Any]) -> dict[str, Any]:
    text = arguments.get("text", "")
    if not isinstance(text, str):
        text = str(text)

    priority_raw = arguments.get("priority", "normal")
    category_raw = arguments.get("category", "progress")
    interrupt_explicit = "interrupt" in arguments
    interrupt = bool(arguments.get("interrupt", False))

    try:
        priority = SpeakPriority(priority_raw)
    except ValueError:
        priority = SpeakPriority.normal
    try:
        category = SpeakCategory(category_raw)
    except ValueError:
        return {
            "content": _json_content(
                {
                    "ok": False,
                    "code": "INTERNAL_ERROR",
                    "engine": None,
                    "queued": False,
                    "message": f"invalid category: {category_raw}",
                }
            ),
            "isError": False,
        }

    req = SpeakRequest(
        text=text,
        priority=priority,
        category=category,
        interrupt=interrupt,
        interrupt_explicit=interrupt_explicit,
    )
    result = await backend.speak(req)
    return {"content": _json_content(result.to_dict()), "isError": False}


async def handle_stop(backend: SpeakBackend, arguments: dict[str, Any]) -> dict[str, Any]:
    clear_queue = bool(arguments.get("clear_queue", True))
    result = await backend.stop(clear_queue=clear_queue)
    return {"content": _json_content(result.to_dict()), "isError": False}
