"""Locale → edge-tts voice mapping tests."""

from __future__ import annotations

from pathlib import Path

from cursor_tts_mcp.config import load_settings
from cursor_tts_mcp.locale_voice import (
    is_auto_voice,
    normalize_locale_tag,
    resolve_edge_voice,
    resolve_locale_voice,
)


def test_normalize_locale_tag():
    assert normalize_locale_tag("zh_CN.UTF-8") == "zh-CN"
    assert normalize_locale_tag("en-US") == "en-US"
    assert normalize_locale_tag("C") is None or normalize_locale_tag("C") == "c"


def test_resolve_edge_voice_prefixes():
    assert resolve_edge_voice("zh-CN").startswith("zh-CN-")
    assert resolve_edge_voice("zh-TW").startswith("zh-TW-")
    assert resolve_edge_voice("en-GB").startswith("en-GB-")
    assert resolve_edge_voice("en-ZZ").startswith("en-")
    assert resolve_edge_voice("ja-JP").startswith("ja-")


def test_voice_map_override():
    voice = resolve_edge_voice("zh-CN", voice_map={"zh-CN": "zh-CN-YunxiNeural"})
    assert voice == "zh-CN-YunxiNeural"


def test_force_locale_env(monkeypatch):
    monkeypatch.setenv("CURSOR_TTS_FORCE_LOCALE", "en-US")
    r = resolve_locale_voice()
    assert r.locale == "en-US"
    assert r.language == "en"
    assert r.voice.startswith("en-")


def test_is_auto_voice():
    assert is_auto_voice("auto")
    assert is_auto_voice("AUTO")
    assert is_auto_voice("")
    assert not is_auto_voice("zh-CN-XiaoxiaoNeural")


def test_load_settings_auto_voice(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text(
        "tts:\n  enabled: true\n  edge:\n    voice: auto\n  locale:\n    auto: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cursor_tts_mcp.config._repo_root", lambda: tmp_path)
    monkeypatch.delenv("CURSOR_TTS_EDGE_VOICE", raising=False)
    monkeypatch.setenv("CURSOR_TTS_FORCE_LOCALE", "ja-JP")
    s = load_settings(tmp_path)
    assert s.resolved_locale == "ja-JP"
    assert s.edge.voice.startswith("ja-")
    assert s.resolved_language == "ja"


def test_explicit_edge_voice_overrides_locale(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text(
        "tts:\n  edge:\n    voice: auto\n  locale:\n    auto: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("cursor_tts_mcp.config._repo_root", lambda: tmp_path)
    monkeypatch.setenv("CURSOR_TTS_FORCE_LOCALE", "en-US")
    monkeypatch.setenv("CURSOR_TTS_EDGE_VOICE", "zh-CN-XiaoxiaoNeural")
    s = load_settings(tmp_path)
    assert s.edge.voice == "zh-CN-XiaoxiaoNeural"
    assert s.resolved_locale == "en-US"
