"""Config loading: env > config/local.yaml > config/default.yaml."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cursor_tts_mcp.locale_voice import (
    is_auto_voice,
    resolve_locale_voice,
)

logger = logging.getLogger("cursor_tts_mcp")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _repo_root() -> Path:
    # src/cursor_tts_mcp/config.py -> parents[2] = repo root
    return Path(__file__).resolve().parents[2]


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return default


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {path}")
    return data


@dataclass
class EngineConfig:
    primary: str = "edge-tts"
    fallback: str = "sapi"
    fallback_enabled: bool = False
    allow_sapi: bool = False


@dataclass
class EdgeConfig:
    timeout_ms: int = 8000
    voice: str = "auto"


@dataclass
class SapiConfig:
    voice: str = ""


@dataclass
class ServiceConfig:
    """P1 local HTTP service."""

    mode: str = "http"  # http | embedded
    url: str = "http://127.0.0.1:18765"
    host: str = "127.0.0.1"
    port: int = 18765
    autostart: bool = True


@dataclass
class PlaybackConfig:
    backend: str = "auto"
    exclusive: bool = True


@dataclass
class LocaleConfig:
    """OS UI language → edge-tts voice."""

    auto: bool = True
    # Optional overrides: {"zh-CN": "zh-CN-YunxiNeural", "en": "en-US-JennyNeural"}
    voice_map: dict[str, str] = field(default_factory=dict)


@dataclass
class TtsSettings:
    enabled: bool = True
    max_chars: int = 80
    queue_size: int = 3
    dedupe_window_ms: int = 5000
    rate: str = "+0%"
    engine: EngineConfig = field(default_factory=EngineConfig)
    edge: EdgeConfig = field(default_factory=EdgeConfig)
    sapi: SapiConfig = field(default_factory=SapiConfig)
    playback: PlaybackConfig = field(default_factory=PlaybackConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    locale: LocaleConfig = field(default_factory=LocaleConfig)
    # Resolved at load time (informational + for speak tool description)
    resolved_locale: str = "zh-CN"
    resolved_language: str = "zh"
    resolved_locale_source: str = "default"
    speak_hint: str = "简体中文短句"
    log_level: str = "INFO"


def _from_mapping(raw: dict[str, Any]) -> TtsSettings:
    t = raw.get("tts", raw)
    engine_raw = t.get("engine") or {}
    edge_raw = t.get("edge") or {}
    sapi_raw = t.get("sapi") or {}
    playback_raw = t.get("playback") or {}
    service_raw = t.get("service") or {}
    locale_raw = t.get("locale") or {}
    voice_map_raw = locale_raw.get("voice_map") or {}
    voice_map = {
        str(k): str(v) for k, v in voice_map_raw.items() if v is not None
    }
    return TtsSettings(
        enabled=_as_bool(t.get("enabled"), True),
        max_chars=int(t.get("max_chars", 80)),
        queue_size=int(t.get("queue_size", 3)),
        dedupe_window_ms=int(t.get("dedupe_window_ms", 5000)),
        rate=str(t.get("rate", "+0%")),
        engine=EngineConfig(
            primary=str(engine_raw.get("primary", "edge-tts")),
            fallback=str(engine_raw.get("fallback", "sapi")),
            fallback_enabled=_as_bool(engine_raw.get("fallback_enabled"), False),
            allow_sapi=_as_bool(engine_raw.get("allow_sapi"), False),
        ),
        edge=EdgeConfig(
            timeout_ms=int(edge_raw.get("timeout_ms", 8000)),
            voice=str(edge_raw.get("voice", "auto")),
        ),
        sapi=SapiConfig(voice=str(sapi_raw.get("voice", ""))),
        playback=PlaybackConfig(
            backend=str(playback_raw.get("backend", "auto")),
            exclusive=_as_bool(playback_raw.get("exclusive"), True),
        ),
        service=ServiceConfig(
            mode=str(service_raw.get("mode", "http")),
            url=str(service_raw.get("url", "http://127.0.0.1:18765")),
            host=str(service_raw.get("host", "127.0.0.1")),
            port=int(service_raw.get("port", 18765)),
            autostart=_as_bool(service_raw.get("autostart"), True),
        ),
        locale=LocaleConfig(
            auto=_as_bool(locale_raw.get("auto"), True),
            voice_map=voice_map,
        ),
        log_level=str(t.get("log_level", "INFO")).upper(),
    )


def _apply_env(settings: TtsSettings) -> TtsSettings:
    if (v := os.environ.get("CURSOR_TTS_ENABLED")) is not None:
        settings.enabled = _as_bool(v, settings.enabled)
    if (v := os.environ.get("CURSOR_TTS_EDGE_VOICE")) is not None:
        settings.edge.voice = v
    if (v := os.environ.get("CURSOR_TTS_SAPI_VOICE")) is not None:
        settings.sapi.voice = v
    if (v := os.environ.get("CURSOR_TTS_MAX_CHARS")) is not None:
        settings.max_chars = int(v)
    if (v := os.environ.get("CURSOR_TTS_EDGE_TIMEOUT_MS")) is not None:
        settings.edge.timeout_ms = int(v)
    if (v := os.environ.get("CURSOR_TTS_FALLBACK")) is not None:
        settings.engine.fallback_enabled = _as_bool(v, settings.engine.fallback_enabled)
    if (v := os.environ.get("CURSOR_TTS_ALLOW_SAPI")) is not None:
        settings.engine.allow_sapi = _as_bool(v, settings.engine.allow_sapi)
    if (v := os.environ.get("CURSOR_TTS_PRIMARY")) is not None:
        settings.engine.primary = v.strip()
    if (v := os.environ.get("CURSOR_TTS_EXCLUSIVE_PLAYBACK")) is not None:
        settings.playback.exclusive = _as_bool(v, settings.playback.exclusive)
    if (v := os.environ.get("CURSOR_TTS_LOG_LEVEL")) is not None:
        settings.log_level = v.upper()
    if (v := os.environ.get("CURSOR_TTS_MODE")) is not None:
        settings.service.mode = v.strip().lower()
    if (v := os.environ.get("CURSOR_TTS_SERVICE_URL")) is not None:
        settings.service.url = v.strip()
    if (v := os.environ.get("CURSOR_TTS_AUTOSTART_SERVICE")) is not None:
        settings.service.autostart = _as_bool(v, settings.service.autostart)
    if (v := os.environ.get("CURSOR_TTS_LOCALE_AUTO")) is not None:
        settings.locale.auto = _as_bool(v, settings.locale.auto)
    return settings


def _resolve_locale_and_voice(settings: TtsSettings) -> TtsSettings:
    """Fill resolved_* and optionally replace edge.voice=auto from OS UI language."""
    forced = os.environ.get("CURSOR_TTS_FORCE_LOCALE")
    resolution = resolve_locale_voice(
        voice_map=settings.locale.voice_map or None,
        forced_locale=forced,
    )
    settings.resolved_locale = resolution.locale
    settings.resolved_language = resolution.language
    settings.resolved_locale_source = resolution.source
    settings.speak_hint = resolution.speak_hint

    explicit_voice_env = os.environ.get("CURSOR_TTS_EDGE_VOICE")
    # Explicit non-auto env voice wins over locale.
    if explicit_voice_env is not None and not is_auto_voice(explicit_voice_env):
        settings.edge.voice = explicit_voice_env.strip()
        logger.info(
            "edge voice from env override=%s (locale=%s ignored for voice)",
            settings.edge.voice,
            settings.resolved_locale,
        )
        return settings

    if settings.locale.auto and is_auto_voice(settings.edge.voice):
        settings.edge.voice = resolution.voice
        logger.info(
            "edge voice from system locale=%s lang=%s voice=%s source=%s",
            settings.resolved_locale,
            settings.resolved_language,
            settings.edge.voice,
            settings.resolved_locale_source,
        )
    elif is_auto_voice(settings.edge.voice):
        # locale.auto=false but voice still auto → fall back to zh neural
        settings.edge.voice = "zh-CN-XiaoxiaoNeural"
        logger.info("locale.auto=false; edge voice defaulted to %s", settings.edge.voice)
    return settings


def setup_logging(level: str = "INFO") -> None:
    """Send logs to stderr (MCP-visible). Idempotent-ish for process lifetime."""
    root = logging.getLogger("cursor_tts_mcp")
    root.handlers.clear()
    handler = logging.StreamHandler()  # stderr
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False


def load_settings(repo_root: Path | None = None) -> TtsSettings:
    root = repo_root or _repo_root()
    default_path = root / "config" / "default.yaml"
    local_path = root / "config" / "local.yaml"

    merged = _load_yaml(default_path)
    local = _load_yaml(local_path)
    if local:
        merged = _deep_merge(merged, local)
        logger.debug("loaded local config: %s", local_path)

    settings = _resolve_locale_and_voice(_apply_env(_from_mapping(merged)))
    return settings
