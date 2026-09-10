"""HTTP service API tests (in-process ASGI)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tts_service.app import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _SilentPlayer:
    """No audio — keep CI/local tests from emitting SAPI."""

    is_playing = False

    async def play_file(self, path: str) -> None:
        return None

    async def speak_sapi(self, text: str, voice: str = "") -> None:
        return None

    async def stop(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_health_and_speak_stop(monkeypatch):
    from cursor_tts_mcp.config import TtsSettings
    import tts_service.app as app_mod
    from cursor_tts_mcp.core.orchestrator import Orchestrator
    from cursor_tts_mcp.engines.base import EngineOutcome

    settings = TtsSettings()
    settings.engine.primary = "edge-tts"
    settings.engine.fallback_enabled = False
    settings.engine.allow_sapi = False
    orch = Orchestrator(settings)
    orch.player = _SilentPlayer()  # type: ignore[assignment]

    async def _fake_speak(text: str):
        return EngineOutcome(engine="edge-tts", mode="file", path=None)

    orch.router.speak = _fake_speak  # type: ignore[method-assign]
    app_mod._orch = orch

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        h = await client.get("/v1/health")
        assert h.status_code == 200 and h.json()["ok"] is True

        s = await client.post(
            "/v1/speak",
            json={"text": "服务层测试", "category": "progress"},
        )
        body = s.json()
        assert body["ok"] is True and body["code"] == "OK"

        st = await client.post("/v1/stop", json={"clear_queue": True})
        assert st.json()["ok"] is True
