# Marketplace submission checklist

Official publish form: https://cursor.com/marketplace/publish

**Public repo:** https://github.com/LrTox/cursor-tts-mcp

## Before submit

- [x] `.cursor-plugin/plugin.json` (name=`cursor-tts`, author=`LrTox`)
- [x] Root `mcp.json` (portable `uvx --from ${PLUGIN_ROOT}`)
- [x] `rules/cursor-tts-speak.mdc`
- [x] `assets/logo.svg`
- [x] `LICENSE` (MIT)
- [x] `README.md` with install/usage
- [x] **Public** GitHub repository: https://github.com/LrTox/cursor-tts-mcp
- [ ] Local smoke: Customize → install Plugin / or `~/.cursor/plugins/local/cursor-tts`
- [ ] Submit repo URL at marketplace/publish (login with your Cursor account)

## Notes for reviewers

- MCP tools: `speak`, `stop`
- Runtime: Python ≥3.11 via `uvx` (install [uv](https://docs.astral.sh/uv/) if missing)
- Default engine: edge-tts (needs network); voice follows OS UI language (`CURSOR_TTS_EDGE_VOICE=auto`)
- Windows primary; macOS/Linux playback backends may vary

## After listing

Ask Cursor to re-index after tag/release updates.
