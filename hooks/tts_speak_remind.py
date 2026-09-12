#!/usr/bin/env python3
"""cursor-tts: force speak for NEW and OLD chats via Hooks.

Timing policy:
- Speak mid-process important content (findings/conclusions/facts), not only start/end.
- Plan subtasks included. Examples in rules are illustrative, not rigid scripts.
- If spoke once at start then more tools ran without speak → keep nudging.

Platform fact: Cursor Rules do NOT hot-reload into an existing chat session.
Hooks do hot-reload and remain the patch path for old chats.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REMINDER = (
    "【cursor-tts 强制】禁止只播开头和结尾。"
    "过程中一旦有重要内容（发现/结论/差异/根因/核对事实/风险/验证结果）必须立刻 MCP speak，短句≤80字。"
    "同一轮应多次 speak。Plan 子任务过程中同样适用。禁止朗读全文。"
)

FOLLOWUP = (
    "【cursor-tts】开头说过不算完：若之后还有重要发现或中间结论却未再 speak，"
    "请立刻补播一句过程要点。禁止只播开头+结尾。"
)

AGENT_NUDGE = (
    "【cursor-tts】中间重要内容也要 speak（发现/结论/事实），不能只说开头和收尾。"
)

_STATE = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "cursor_tts_hook_state.json"
_TTS_URL = os.environ.get("CURSOR_TTS_SERVICE_URL", "http://127.0.0.1:18765").rstrip("/")
_AUTO_SPEAK = os.environ.get("CURSOR_TTS_HOOK_AUTO_SPEAK", "true").lower() not in (
    "0",
    "false",
    "no",
    "off",
)

_PLAN_MODE_VALUES = frozenset({"plan", "planning", "ask"})
_PLAN_TOOL_RE = re.compile(
    r"createplan|create_plan|switchmode|switch_mode|todowrite|todo_write|"
    r"askquestion|ask_question",
    re.I,
)
_PLAN_TEXT_RE = re.compile(
    r"(?i)(\bplan\s*mode\b|creating\s+plan|createplan|"
    r"##\s*plan\b|实施计划|计划模式|正在制定计划|"
    r"切换到\s*plan|entered\s+plan)",
)


def _load() -> dict:
    try:
        if _STATE.is_file():
            return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    try:
        now = time.time()
        # Only prune timestamp-like values. Flags such as planmode=1 must NOT be
        # treated as epoch seconds (or they vanish immediately as "stale").
        ts_prefixes = (
            "turn:",
            "spoke:",
            "tools:",
            "autotts:",
            "autospoke:",
            "prenudge:",
            "postctx:",
            "sub:",
            "stopfix:",
            "midnudge:",
        )
        pruned: dict = {}
        for k, v in data.items():
            key = str(k)
            if any(key.startswith(p) for p in ts_prefixes) and isinstance(v, (int, float)):
                if now - float(v) > 21600:
                    continue
            pruned[k] = v
        _STATE.write_text(json.dumps(pruned), encoding="utf-8")
    except Exception:
        pass


def _allow(key: str, cooldown_s: float) -> bool:
    data = _load()
    now = time.time()
    last = float(data.get(key, 0) or 0)
    if now - last < cooldown_s:
        return False
    data[key] = now
    _save(data)
    return True


def _set(key: str, value: float | int | str) -> None:
    data = _load()
    data[key] = value
    _save(data)


def _get(key: str, default: float = 0.0) -> float:
    data = _load()
    try:
        return float(data.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _get_str(key: str, default: str = "") -> str:
    data = _load()
    val = data.get(key, default)
    return "" if val is None else str(val)


def _read_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _tool_name(payload: dict) -> str:
    return str(
        payload.get("tool_name")
        or payload.get("toolName")
        or payload.get("tool")
        or ""
    )


def _session(payload: dict) -> str:
    return str(payload.get("session_id") or payload.get("conversation_id") or "global")


def _payload_blob(payload: dict) -> str:
    parts = [
        _tool_name(payload),
        str(payload.get("mcp_server_name") or ""),
        str(payload.get("mcpServerName") or ""),
        str(payload.get("server") or ""),
        str(payload.get("namespace") or ""),
        str(payload.get("toolName") or ""),
    ]
    for key in ("tool_input", "input", "arguments", "updated_input", "text"):
        val = payload.get(key)
        if val is None:
            continue
        try:
            parts.append(json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val)
        except Exception:
            parts.append(str(val))
    return " ".join(parts).lower()


def _mode_from_payload(payload: dict) -> str:
    keys = (
        "mode",
        "composer_mode",
        "composerMode",
        "agent_mode",
        "agentMode",
        "chat_mode",
        "chatMode",
        "conversation_mode",
        "conversationMode",
        "generation_mode",
        "generationMode",
    )
    for key in keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    for nest_key in ("composer", "session", "context", "metadata", "status"):
        nest = payload.get(nest_key)
        if not isinstance(nest, dict):
            continue
        for key in keys:
            val = nest.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
    return ""


def _track_plan_mode_from_tool(session: str, payload: dict) -> None:
    """Infer plan/agent transitions from SwitchMode / CreatePlan tool calls."""
    name = _tool_name(payload).lower().replace("_", "")
    blob = _payload_blob(payload)

    if "createplan" in name or "createplan" in blob.replace("_", ""):
        _set(f"planmode:{session}", 1)
        return

    if "switchmode" in name or "switchmode" in blob.replace("_", ""):
        # target_mode_id / targetModeId / mode
        if re.search(r"(target[_ ]?mode[_ ]?id|mode)\s*[\"':=\s]+agent\b", blob):
            _set(f"planmode:{session}", 0)
            return
        if re.search(r"(target[_ ]?mode[_ ]?id|mode)\s*[\"':=\s]+plan\b", blob):
            _set(f"planmode:{session}", 1)
            return
        if "plan" in blob and "agent" not in blob:
            _set(f"planmode:{session}", 1)
            return
        if re.search(r"\bagent\b", blob) and "plan" not in blob:
            _set(f"planmode:{session}", 0)


def _is_plan_mode(session: str, payload: dict, *, text: str = "") -> bool:
    mode = _mode_from_payload(payload)
    if mode in _PLAN_MODE_VALUES:
        _set(f"planmode:{session}", 1)
        return True
    if mode in {"agent", "edit", "code"}:
        _set(f"planmode:{session}", 0)
        return False

    if _get(f"planmode:{session}") >= 1:
        return True

    blob = (_payload_blob(payload) + " " + (text or "")).lower()
    name = _tool_name(payload)
    if _PLAN_TOOL_RE.search(name) or _PLAN_TOOL_RE.search(blob):
        # TodoWrite alone is ambiguous (also used in agent). Only lock plan when
        # CreatePlan / SwitchMode(plan) / explicit plan text is present.
        compact = blob.replace("_", "")
        if "createplan" in compact or "switchmode" in compact or _PLAN_TEXT_RE.search(blob):
            _set(f"planmode:{session}", 1)
            return True

    if text and _PLAN_TEXT_RE.search(text):
        return True

    return False


def _is_plan_related_tool(payload: dict) -> bool:
    name = _tool_name(payload)
    blob = _payload_blob(payload)
    if _PLAN_TOOL_RE.search(name):
        return True
    compact = blob.replace("_", "")
    return "createplan" in compact or (
        "switchmode" in compact and "plan" in compact
    )


def _is_speak_tool(payload: dict) -> bool:
    blob = _payload_blob(payload)
    name = _tool_name(payload).lower()
    if "stop" in name and "speak" not in name:
        return False
    if "cursor-tts" in blob and "stop" in blob and "speak" not in blob:
        return False
    return ("speak" in blob) or ("cursor-tts" in blob and "stop" not in blob)


def _mark_spoke(session: str) -> None:
    _set(f"spoke:{session}", time.time())
    _set(f"toolcount:{session}", 0)


def _mark_tool_use(session: str) -> None:
    _set(f"tools:{session}", time.time())
    try:
        n = int(_get(f"toolcount:{session}", 0))
    except (TypeError, ValueError):
        n = 0
    _set(f"toolcount:{session}", n + 1)


def _toolcount(session: str) -> int:
    try:
        return int(_get(f"toolcount:{session}", 0))
    except (TypeError, ValueError):
        return 0


def _already_spoke(session: str) -> bool:
    """True if speak happened at least once this user turn."""
    turn = _get(f"turn:{session}")
    spoke = _get(f"spoke:{session}")
    return spoke > 0 and (turn <= 0 or spoke >= turn)


def _needs_mid_process_nudge(session: str) -> bool:
    """True when work continued after last speak — force mid-content reminders.

    Fixes the failure mode: speak once at start, then silent until the end.
    """
    count = _toolcount(session)
    spoke = _get(f"spoke:{session}")
    turn = _get(f"turn:{session}")
    if count <= 0:
        return False
    # Never spoke this turn after tools → need speak
    if spoke <= 0 or (turn > 0 and spoke < turn):
        return True
    # Spoke earlier, but more tools ran without a fresh speak
    age = time.time() - spoke
    return count >= 2 or age >= 35.0


def _summarize_for_speech(text: str, *, max_chars: int = 78) -> str:
    """Build a short spoken line from assistant text (never full dump).

    Prefer a complete sentence under max_chars; avoid hard-cutting at 40 which
    made utterances sound incomplete.
    """
    if not text:
        return ""
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"```[\s\S]*?```", " ", cleaned)
    cleaned = re.sub(r"`[^`]+`", " ", cleaned)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[#>*_\-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[。！？；.!?;])\s*", cleaned)
    line = ""
    for p in parts:
        p = p.strip()
        if len(p) < 4:
            continue
        line = p
        break
    if not line:
        line = cleaned
    if len(line) <= max_chars:
        return line
    # Prefer cut at last punctuation inside budget
    chunk = line[:max_chars]
    for sep in ("。", "！", "？", "；", ";", ".", "!", "?", "，", ","):
        idx = chunk.rfind(sep)
        if idx >= 12:
            return chunk[: idx + 1]
    return chunk.rstrip() + "…"


def _looks_like_plan_document(text: str) -> bool:
    """True for full plan drafts — not short Plan-subtask progress lines."""
    if not text:
        return False
    boxes = len(re.findall(r"^\s*[-*]\s*\[[ xX]\]", text, flags=re.M))
    headers = len(re.findall(r"^#{1,3}\s+", text, flags=re.M))
    if boxes >= 3 and headers >= 2:
        return True
    if _PLAN_TEXT_RE.search(text) and (boxes >= 2 or headers >= 3 or len(text) > 800):
        return True
    return False


def _http_speak(text: str, *, category: str = "summary") -> bool:
    payload = json.dumps(
        {
            "text": text,
            "priority": "normal",
            "category": category,
            "interrupt": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{_TTS_URL}/v1/speak",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return bool(body.get("ok"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def _auto_speak_response(session: str, text: str, payload: dict) -> None:
    if not _AUTO_SPEAK:
        return
    if _looks_like_plan_document(text):
        return
    # Avoid stacking a truncated auto-line right after a real MCP speak (sounds cut-off).
    spoke = _get(f"spoke:{session}")
    if spoke > 0 and (time.time() - spoke) < 8.0:
        return
    # Allow again when work continued after last speak (mid-process gap).
    if _already_spoke(session) and not _needs_mid_process_nudge(session):
        return
    turn = _get(f"turn:{session}")
    tools = _get(f"tools:{session}")
    if tools <= 0 or (turn > 0 and tools < turn):
        return
    summary = _summarize_for_speech(text)
    if len(summary) < 4:
        return
    if not _allow(f"autotts:{session}", 10.0):
        return
    ok = _http_speak(summary, category="progress")
    if ok:
        _mark_spoke(session)
        _set(f"autospoke:{session}", time.time())


def main() -> None:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = _read_stdin()
    session = _session(payload)

    if event == "sessionStart":
        _set(f"turn:{session}", time.time())
        _set(f"spoke:{session}", 0)
        _set(f"tools:{session}", 0)
        _set(f"toolcount:{session}", 0)
        mode = _mode_from_payload(payload)
        if mode in _PLAN_MODE_VALUES:
            _set(f"planmode:{session}", 1)
        elif mode in {"agent", "edit", "code"}:
            _set(f"planmode:{session}", 0)
        print(json.dumps({"additional_context": REMINDER}, ensure_ascii=False))
        return

    if event == "beforeSubmitPrompt":
        _set(f"turn:{session}", time.time())
        _set(f"spoke:{session}", 0)
        _set(f"tools:{session}", 0)
        _set(f"toolcount:{session}", 0)
        mode = _mode_from_payload(payload)
        if mode in _PLAN_MODE_VALUES:
            _set(f"planmode:{session}", 1)
        elif mode in {"agent", "edit", "code"}:
            _set(f"planmode:{session}", 0)
        print(json.dumps({"continue": True}))
        return

    if event == "preToolUse":
        _track_plan_mode_from_tool(session, payload)
        if _is_speak_tool(payload):
            _mark_spoke(session)
            print("{}")
            return
        _mark_tool_use(session)
        cooldown = 35.0 if _needs_mid_process_nudge(session) else 75.0
        if not _allow(f"prenudge:{session}", cooldown):
            print("{}")
            return
        print(json.dumps({"agent_message": AGENT_NUDGE}, ensure_ascii=False))
        return

    if event == "afterMCPExecution":
        _track_plan_mode_from_tool(session, payload)
        if _is_speak_tool(payload):
            _mark_spoke(session)
        else:
            _mark_tool_use(session)
        print("{}")
        return

    if event == "postToolUse":
        _track_plan_mode_from_tool(session, payload)
        if _is_speak_tool(payload):
            _mark_spoke(session)
            print("{}")
            return
        _mark_tool_use(session)
        cooldown = 25.0 if _needs_mid_process_nudge(session) else 55.0
        if not _allow(f"postctx:{session}", cooldown):
            print("{}")
            return
        msg = FOLLOWUP if _needs_mid_process_nudge(session) else REMINDER
        print(json.dumps({"additional_context": msg}, ensure_ascii=False))
        return

    if event == "afterAgentResponse":
        text = str(payload.get("text") or "")
        if _looks_like_plan_document(text):
            print("{}")
            return
        _auto_speak_response(session, text, payload)
        print("{}")
        return

    if event == "subagentStop":
        _mark_tool_use(session)
        if not _allow(f"sub:{session}", 45.0):
            print("{}")
            return
        print(json.dumps({"followup_message": FOLLOWUP}, ensure_ascii=False))
        return

    if event == "stop":
        status = str(payload.get("status") or "")
        loop_count = int(payload.get("loop_count") or 0)
        if status != "completed" or loop_count > 0:
            print("{}")
            return
        turn = _get(f"turn:{session}")
        tools = _get(f"tools:{session}")
        if tools <= 0 or (turn > 0 and tools < turn):
            print("{}")
            return
        # Spoke only at start, then more tools → still follow up for mid content.
        if _already_spoke(session) and not _needs_mid_process_nudge(session):
            print("{}")
            return
        if not _allow(f"stopfix:{session}", 45.0):
            print("{}")
            return
        print(json.dumps({"followup_message": FOLLOWUP}, ensure_ascii=False))
        return

    print("{}")


if __name__ == "__main__":
    main()
