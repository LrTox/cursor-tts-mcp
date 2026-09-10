"""Orchestrator behavior tests with fake router/player."""

from __future__ import annotations

import asyncio

import pytest

from cursor_tts_mcp.config import TtsSettings
from cursor_tts_mcp.core.orchestrator import Orchestrator
from cursor_tts_mcp.engines.base import EngineOutcome
from cursor_tts_mcp.models import SpeakCategory, SpeakRequest


class FakeRouter:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.delay = 0.05
        self.fail = False

    async def speak(self, text: str) -> EngineOutcome:
        if self.fail:
            raise RuntimeError("boom")
        self.texts.append(text)
        await asyncio.sleep(self.delay)
        return EngineOutcome(mode="direct", engine="fake")


class FakePlayer:
    def __init__(self) -> None:
        self._playing = False
        self.stopped = 0

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def stop(self) -> bool:
        was = self._playing
        self._playing = False
        self.stopped += 1
        return was


@pytest.fixture
def orch() -> Orchestrator:
    settings = TtsSettings()
    settings.dedupe_window_ms = 5000
    settings.queue_size = 3
    o = Orchestrator(settings)
    o.router = FakeRouter()  # type: ignore[assignment]
    o.player = FakePlayer()  # type: ignore[assignment]
    return o


@pytest.mark.asyncio
async def test_disabled(orch: Orchestrator):
    orch.settings.enabled = False
    r = await orch.speak(SpeakRequest(text="你好"))
    assert r.code == "DISABLED" and r.ok is False


@pytest.mark.asyncio
async def test_invalid_and_too_long(orch: Orchestrator):
    r1 = await orch.speak(SpeakRequest(text="  "))
    assert r1.code == "INVALID_TEXT"
    r2 = await orch.speak(SpeakRequest(text="啊" * 81))
    assert r2.code == "TEXT_TOO_LONG"


@pytest.mark.asyncio
async def test_accept_and_dedupe(orch: Orchestrator):
    r1 = await orch.speak(SpeakRequest(text="步骤完成"))
    assert r1.code == "OK" and r1.queued is False
    r2 = await orch.speak(SpeakRequest(text="步骤完成"))
    assert r2.code == "DEDUPED" and r2.ok is True
    await asyncio.sleep(0.15)
    assert orch.router.texts == ["步骤完成"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_error_defaults_interrupt(orch: Orchestrator):
    orch.router.delay = 0.3  # type: ignore[attr-defined]
    r1 = await orch.speak(SpeakRequest(text="长任务进行中"))
    assert r1.code == "OK"
    await asyncio.sleep(0.05)
    r2 = await orch.speak(
        SpeakRequest(
            text="构建失败了",
            category=SpeakCategory.error,
            interrupt_explicit=False,
            interrupt=False,
        )
    )
    assert r2.code == "OK"
    assert orch.player.stopped >= 1  # type: ignore[attr-defined]
    await asyncio.sleep(0.4)
    assert "构建失败了" in orch.router.texts  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_queue_overflow_drops_oldest(orch: Orchestrator):
    orch.router.delay = 0.2  # type: ignore[attr-defined]
    await orch.speak(SpeakRequest(text="playing"))
    await asyncio.sleep(0.02)
    for i in range(5):
        await orch.speak(SpeakRequest(text=f"q{i}"))
    await asyncio.sleep(1.5)
    texts = orch.router.texts  # type: ignore[attr-defined]
    assert "playing" in texts
    # waiting capacity 3 → oldest waiting dropped; newest kept
    assert "q0" not in texts or texts.count("q0") == 0
    assert "q4" in texts
    queued_spoken = [t for t in texts if t.startswith("q")]
    assert len(queued_spoken) <= 3


@pytest.mark.asyncio
async def test_stop_idle(orch: Orchestrator):
    r = await orch.stop()
    assert r.code == "NOT_PLAYING" and r.ok is True
