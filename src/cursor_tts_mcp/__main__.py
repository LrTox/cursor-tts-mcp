"""Entry: python -m cursor_tts_mcp"""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    from cursor_tts_mcp.server import run

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
