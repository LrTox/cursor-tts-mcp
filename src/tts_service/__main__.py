"""Run: python -m tts_service"""

from __future__ import annotations

import logging

import uvicorn

from cursor_tts_mcp.config import load_settings, setup_logging


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    host = settings.service.host
    port = settings.service.port
    logging.getLogger("cursor_tts_mcp.tts_service").info(
        "starting tts_service on %s:%s", host, port
    )
    uvicorn.run(
        "tts_service.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
