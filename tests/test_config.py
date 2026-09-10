"""Config loading tests."""

from __future__ import annotations

import os
from pathlib import Path

from cursor_tts_mcp.config import load_settings


def test_load_default(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text(
        "tts:\n  enabled: true\n  max_chars: 40\n  edge:\n    voice: v1\n  sapi:\n    voice: ''\n",
        encoding="utf-8",
    )
    # point loader at tmp by monkeypatching repo root helper
    monkeypatch.setattr(
        "cursor_tts_mcp.config._repo_root", lambda: tmp_path
    )
    monkeypatch.delenv("CURSOR_TTS_MAX_CHARS", raising=False)
    s = load_settings(tmp_path)
    assert s.max_chars == 40
    assert s.edge.voice == "v1"


def test_env_overrides(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "default.yaml").write_text(
        "tts:\n  enabled: true\n  max_chars: 80\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CURSOR_TTS_MAX_CHARS", "50")
    monkeypatch.setenv("CURSOR_TTS_ENABLED", "false")
    monkeypatch.setenv("CURSOR_TTS_FALLBACK", "0")
    s = load_settings(tmp_path)
    assert s.max_chars == 50
    assert s.enabled is False
    assert s.engine.fallback_enabled is False
