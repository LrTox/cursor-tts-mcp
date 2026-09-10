# cursor-tts MCP

Progress-triggered TTS for Cursor Agent (`speak` / `stop`). Voice follows the **system UI language** (edge-tts; Windows-first).

## Marketplace / Plugin install

Requires [uv](https://docs.astral.sh/uv/) (`uvx`).

| Way | Steps |
| --- | --- |
| **Cursor Marketplace** | After listing: search `cursor-tts` in Cursor |
| **Local Plugin** | Clone repo → Cursor: add local plugin / copy into `~/.cursor/plugins/local/cursor-tts` |
| **Manual MCP** | Point MCP at `uvx --from <this-repo> cursor-tts-mcp` (see root `mcp.json`) |

Plugin layout:

- `.cursor-plugin/plugin.json`
- `mcp.json` (`uvx --from ${PLUGIN_ROOT}`)
- `rules/cursor-tts-speak.mdc`
- `assets/logo.svg`

Submit checklist: [docs/guide/Marketplace提交清单.md](docs/guide/Marketplace提交清单.md) · Form: https://cursor.com/marketplace/publish

## Docs

See [docs/README.md](docs/README.md).

## Quick start (dev)

```powershell
cd E:\WorkSpace\mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Default Marketplace mode is **embedded** (MCP process speaks). Optional P1: `tts_service` on `127.0.0.1:18765` + thin HTTP client.

```powershell
# optional standalone service
python -m tts_service
```

Local Cursor wiring:

- `.cursor/mcp.json` → MCP `cursor-tts`
- `.cursor/rules/cursor-tts-speak.mdc` → speak-on-progress rule

If tools missing: reload MCP / restart Cursor. See `docs/guide/Cursor接入与配置说明.md`.

## Layout

```text
.cursor-plugin/       # Marketplace plugin manifest
mcp.json              # Portable MCP launch for Plugin
rules/                # Agent rule shipped with Plugin
src/cursor_tts_mcp/   # MCP + orchestrator + engines + playback
config/default.yaml   # defaults
docs/                 # design & contracts
tests/
```
