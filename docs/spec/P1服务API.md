# P1 TTS 本地服务 API

| 项 | 内容 |
|---|---|
| 版本 | v1.0 |
| 绑定 | `127.0.0.1:18765`（可配） |
| 对应 | [技术架构](../design/TTS播报技术架构设计.md) §9 |

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/health` | 健康检查 |
| POST | `/v1/speak` | 受理播报（契约字段同 MCP `speak`） |
| POST | `/v1/stop` | 停止（同 MCP `stop`） |

### GET `/v1/health`

```json
{"ok": true, "service": "tts_service", "version": "0.1.0"}
```

### POST `/v1/speak`

请求体与 MCP `speak` 入参一致；响应体与 MCP `speak` JSON 契约一致。

### POST `/v1/stop`

```json
{"clear_queue": true}
```

响应与 MCP `stop` 契约一致。

## 启动

```powershell
python -m tts_service
```

MCP 在 `tts.service.mode=http` 且 `autostart=true` 时，会在服务未就绪时自动拉起该进程。  
服务不可用时 MCP **不**回退本进程播放（避免双播放器），返回 `INTERNAL_ERROR` 与明确 message。

## 模式

| `tts.service.mode` | 行为 |
|--------------------|------|
| `http`（默认） | MCP → HTTP → tts_service |
| `embedded` | MCP 进程内 Orchestrator（单测/应急） |

环境变量：`CURSOR_TTS_MODE`、`CURSOR_TTS_SERVICE_URL`、`CURSOR_TTS_AUTOSTART_SERVICE`。
