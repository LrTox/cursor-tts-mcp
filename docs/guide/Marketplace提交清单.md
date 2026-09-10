# Marketplace submission checklist

Official publish form: https://cursor.com/marketplace/publish

## Before submit

- [x] `.cursor-plugin/plugin.json` (name=`cursor-tts`)
- [x] Root `mcp.json` (portable `uvx --from ${PLUGIN_ROOT}`)
- [x] `rules/cursor-tts-speak.mdc`
- [x] `assets/logo.svg`
- [x] `LICENSE` (MIT)
- [x] `README.md` with install/usage
- [ ] **Public** GitHub repository URL
- [ ] Local test: Customize → install / or `~/.cursor/plugins/local/cursor-tts`
- [ ] Submit repo link at marketplace/publish (Cursor account login)

## Notes for reviewers

- MCP tools: `speak`, `stop`
- Runtime: Python ≥3.11 via `uvx` (install [uv](https://docs.astral.sh/uv/) if missing)
- Default engine: edge-tts (needs network); voice follows OS UI language (`CURSOR_TTS_EDGE_VOICE=auto`)
- Windows primary; macOS/Linux playback backends may vary

## After listing

Ask Cursor to re-index after tag/release updates.
