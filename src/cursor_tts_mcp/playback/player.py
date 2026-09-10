"""Playback subprocess gate — killable player with optional cross-process mutex."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("cursor_tts_mcp.playback")

_PID_FILE = Path(tempfile.gettempdir()) / "cursor_tts_mcp.player.pid"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> None:
    if not _pid_alive(pid):
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.kill(pid, 9)
    except Exception:
        logger.debug("foreign player kill failed pid=%s", pid, exc_info=True)


class Player:
    """At most one play subprocess; stop() kills it. Optional OS-wide exclusive."""

    def __init__(self, *, exclusive: bool = True) -> None:
        self._proc: subprocess.Popen[Any] | None = None
        self._lock = asyncio.Lock()
        self._exclusive = exclusive

    @property
    def is_playing(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def _claim_exclusive(self) -> None:
        if not self._exclusive:
            return
        try:
            if _PID_FILE.is_file():
                raw = _PID_FILE.read_text(encoding="utf-8").strip()
                old = int(raw) if raw.isdigit() else 0
                if old and old != os.getpid() and _pid_alive(old):
                    logger.info("exclusive: stopping foreign player pid=%s", old)
                    _kill_pid(old)
        except Exception:
            logger.debug("exclusive claim read failed", exc_info=True)

    def _remember_pid(self, pid: int) -> None:
        if not self._exclusive:
            return
        try:
            _PID_FILE.write_text(str(pid), encoding="utf-8")
        except Exception:
            logger.debug("exclusive pid write failed", exc_info=True)

    def _clear_pid_if_ours(self, pid: int | None) -> None:
        if not self._exclusive or pid is None:
            return
        try:
            if _PID_FILE.is_file():
                raw = _PID_FILE.read_text(encoding="utf-8").strip()
                if raw == str(pid):
                    _PID_FILE.unlink(missing_ok=True)
        except Exception:
            logger.debug("exclusive pid clear failed", exc_info=True)

    async def play_file(self, path: str) -> None:
        async with self._lock:
            await self._kill_unlocked()
            self._claim_exclusive()
            script = (
                f"$p = {path!r};"
                "Add-Type -AssemblyName presentationCore;"
                "$m = New-Object System.Windows.Media.MediaPlayer;"
                "$m.Open([uri]$p);"
                "Start-Sleep -Milliseconds 200;"
                "$m.Play();"
                "while ($m.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 50 };"
                "$dur = $m.NaturalDuration.TimeSpan.TotalMilliseconds;"
                "Start-Sleep -Milliseconds ([Math]::Max(200, [int]$dur + 300));"
                "$m.Close();"
            )
            self._proc = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._remember_pid(self._proc.pid)
            logger.info("player started pid=%s path=%s", self._proc.pid, path)

        proc = self._proc
        if proc is None:
            return
        await asyncio.to_thread(proc.wait)
        async with self._lock:
            if self._proc is proc:
                self._proc = None
            self._clear_pid_if_ours(proc.pid)

    async def speak_sapi(self, text: str, voice: str = "") -> None:
        """Speak via SAPI in a killable PowerShell child process."""
        async with self._lock:
            await self._kill_unlocked()
            self._claim_exclusive()
            voice_line = ""
            if voice.strip():
                voice_line = (
                    f"$target = {voice!r};"
                    "$v = $speak.GetVoices() | Where-Object { $_.GetDescription() -like \"*$target*\" } | Select-Object -First 1;"
                    "if ($v) { $speak.Voice = $v }"
                )
            ps_text = text.replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"{voice_line};"
                f"$speak.Speak('{ps_text}');"
            )
            self._proc = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._remember_pid(self._proc.pid)
            logger.info("sapi player started pid=%s", self._proc.pid)

        proc = self._proc
        if proc is None:
            return
        await asyncio.to_thread(proc.wait)
        async with self._lock:
            if self._proc is proc:
                self._proc = None
            self._clear_pid_if_ours(proc.pid)

    async def stop(self) -> bool:
        async with self._lock:
            return await self._kill_unlocked()

    async def _kill_unlocked(self) -> bool:
        proc = self._proc
        self._proc = None
        if proc is None:
            return False
        pid = proc.pid
        if proc.poll() is not None:
            self._clear_pid_if_ours(pid)
            return False
        logger.info("killing player pid=%s", pid)
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await asyncio.to_thread(proc.wait)
        except Exception:
            logger.exception("terminate failed; killing")
            try:
                proc.kill()
            except Exception:
                pass
        self._clear_pid_if_ours(pid)
        return True
