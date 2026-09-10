# Cursor Agent TTS 播报技术架构设计

| 项 | 内容 |
|---|---|
| 版本 | v0.4 |
| 状态 | 草案 |
| 对应功能设计 | [TTS播报功能设计.md](./TTS播报功能设计.md) |
| 主路径 | A → C（P0 单进程 MCP → P1 本地服务拆分） |

---

## 1. 设计目标与约束

### 1.1 技术目标

1. **低延迟受理**：`speak` 尽快返回 MCP 结果，合成/播放在后台进行，避免拖慢 Agent。
2. **可中断**：`stop` 能杀掉当前播放进程并清空短队列。
3. **可降级**：`edge-tts` 失败/超时自动切 Windows SAPI。
4. **可演进**：P0 模块边界预留引擎接口与编排层，P1 仅下沉「编排 + 引擎 + 播放」，MCP 变薄客户端。
5. **薄自研**：不 fork 开源整仓；按需借鉴播放/队列思路。

### 1.2 约束

| 约束 | 说明 |
|------|------|
| 运行环境 | Windows 10+（P0 必保）；macOS 不在 P0/P1 范围 |
| 接入方式 | Cursor MCP，`stdio` 传输 |
| 触发方式 | Agent 按进展主动调工具（规则层），非默认全文朗读 |
| 进程模型 P0 | 单进程即可 |
| 安全 | 仅本机；不对外暴露端口（P1 仅 `127.0.0.1`） |

---

## 2. 技术选型（锁定）

| 层级 | 选型 | 理由 |
|------|------|------|
| 语言 | **Python 3.11+** | `edge-tts` 生态成熟；SAPI/COM 调用简单；官方 MCP Python SDK 完备 |
| MCP SDK | `mcp`（官方 Python） | stdio Server、tools 注册标准 |
| 主引擎 | `edge-tts` | 中文音质好；输出音频文件后本地播放 |
| 兜底引擎 | Windows **SAPI**（优先 **PowerShell 子进程** 发音以便 kill；可用 COM 作备选实现细节） | 离线、低依赖；与可中断模型一致 |
| 播放控制 | **子进程播放 + kill** | `stop` 可硬中断；避免难以取消的库内阻塞 |
| 异步模型 | `asyncio` | 与 MCP Python SDK 一致；合成与编排协程化 |
| 配置 | `config/default.yaml` + 可选 `local.yaml` + 环境变量 | 简单可改，无需配置中心 |
| 日志 | 标准库 `logging` → **stderr** | P0 必打引擎名/失败；P1 增强 category 等字段 |
| 打包运行 | `pyproject.toml`；Cursor 用 `python -m cursor_tts_mcp` 启动 | 与薄 MCP 定位一致 |
| 主要依赖 | `mcp`、`edge-tts`；SAPI 优先 PowerShell 子进程（可选再加 `pywin32`） | 写入 `pyproject.toml` 时遵守本表 |

### 2.1 明确不采用（P0/P1）

- Node/TS 作为主实现（`edge-tts` 主路径不划算）
- 默认硬依赖 ffplay/ffmpeg（可作为可选增强）
- 付费云 TTS SDK
- 整仓 fork 第三方 TTS/Hook 项目

### 2.2 播放器选择（Windows）

优先级：

1. **PowerShell + .NET 播放**（系统自带，独立进程，可 kill）
2. edge 产出格式兼容性不足时：统一封装转换或改用可播格式；SAPI 路径直接发音、不经文件
3. 可选：`ffplay`（用户已安装时）

**原则**：播放必须跑在**可杀子进程**中，编排层持有进程句柄。

---

## 3. 逻辑架构

### 3.1 P0 逻辑视图

```
┌──────────────────────────────────────────────────────────┐
│                    Cursor Agent                          │
│         User Rule → tools/call: speak | stop             │
└───────────────────────────┬──────────────────────────────┘
                            │ MCP stdio (JSON-RPC)
┌───────────────────────────▼──────────────────────────────┐
│                 cursor-tts-mcp（单进程）                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ MCP Adapter │→ │ Orchestrator │→ │ Engine Router   │  │
│  │ speak/stop  │  │ 校验/队列/   │  │ primary→fallback│  │
│  └─────────────┘  │ 中断/去重    │  └────────┬────────┘  │
│                   └──────┬───────┘           │           │
│                          │         ┌─────────┴─────────┐ │
│                          │         ▼                   ▼ │
│                          │   EdgeTtsEngine      SapiEngine│
│                          │         │                   │ │
│                          └─────────┼───────────────────┘ │
│                                    ▼                     │
│                             PlaybackGate                 │
│                          (子进程 play + kill)            │
└──────────────────────────────────────────────────────────┘
```

### 3.2 P1 逻辑视图（演进，不改工具语义）

```
Cursor Agent
    │ MCP stdio
    ▼
MCP Adapter（薄）──HTTP──► TTS Local Service (127.0.0.1)
                              ├─ Orchestrator + Queue
                              ├─ Engine Router
                              └─ PlaybackGate
可选：Cursor Hook（调研后可选，默认关）──► 同一 Service
```

说明：P1 Hook **不是 MCP 自带能力**，取决于 Cursor Hooks 是否可调用本服务；不可用则跳过，不影响 `speak`/`stop` 主路径。

P1 保证：`speak`/`stop` 的 MCP 契约不变；仅把编排与播放迁出进程。

---

## 4. 模块划分与目录结构

### 4.1 建议仓库结构（P0）

```text
mcp/
├── docs/
│   ├── design/
│   ├── spec/
│   ├── guide/
│   ├── plan/
│   └── qa/
├── config/
│   └── default.yaml
├── src/
│   └── cursor_tts_mcp/
│       ├── __init__.py
│       ├── __main__.py              # python -m cursor_tts_mcp
│       ├── server.py                # MCP 注册与生命周期
│       ├── config.py                # 配置加载与校验
│       ├── models.py                # SpeakRequest / SpeakResult 等
│       ├── tools/
│       │   ├── speak.py
│       │   └── stop.py
│       ├── core/
│       │   ├── orchestrator.py      # 受理、短队列、中断、去重
│       │   └── text_policy.py       # 长度校验（拒绝超限）、normalize、空文本
│       ├── engines/
│       │   ├── base.py              # Protocol / ABC
│       │   ├── edge_tts_engine.py
│       │   ├── sapi_engine.py
│       │   └── router.py            # primary → fallback
│       └── playback/
│           └── player.py            # 启停子进程
├── tests/
│   ├── test_text_policy.py
│   ├── test_orchestrator.py
│   └── test_router.py
├── pyproject.toml
└── README.md
```

### 4.2 模块职责

| 模块 | 职责 | 不负责 |
|------|------|--------|
| `server` | MCP stdio 生命周期、工具注册 | 引擎细节 |
| `tools/*` | 参数解析、调用编排层、映射返回 | 播放实现 |
| `orchestrator` | 校验、短队列、interrupt、stop、异步投递 | 具体 TTS API |
| `text_policy` | max_chars、空串、空白规范化 | I/O |
| `engines.*` | 合成或直接发音；超时 | 队列策略 |
| `playback.player` | 播文件、kill | 选引擎 |
| `config` | 合并默认与环境变量 | 业务分支 |

### 4.3 依赖方向

```
tools → core → engines → playback
tools → models
core  → models, config
server → tools, core, config

禁止：engines → tools；playback → engines；core → server
```

---

## 5. 关键路径与时序

### 5.1 `speak`（进展播报，快速返回）

```
Agent                MCP Adapter           Orchestrator          Router/Engine         Player
  │                      │                      │                     │                   │
  │ tools/call speak     │                      │                     │                   │
  │─────────────────────►│                      │                     │                   │
  │                      │ accept(req)          │                     │                   │
  │                      │─────────────────────►│                     │                   │
  │                      │                      │ validate + enqueue  │                   │
  │                      │                      │ spawn bg task       │                   │
  │                      │◄──── SpeakResult ────│                     │                   │
  │◄──── ok, queued ─────│                      │                     │                   │
  │                      │                      │ synthesize          │                   │
  │                      │                      │────────────────────►│                   │
  │                      │                      │◄── audio|spoken ────│                   │
  │                      │                      │ play (subprocess)   │                   │
  │                      │                      │─────────────────────────────────────────►│
  │                      │                      │                     │                   │▶ audible
```

要点：

- MCP 响应在「受理成功」后返回，不等待播放结束。
- `interrupt=true` 时：**kill 当前 + 清空队列 + 再播新句**（与契约一致）。
- `category=error` 且未显式传 `interrupt` 时，tool 层默认 `interrupt=true`。

### 5.2 `stop`

```
Agent → stop → Orchestrator.cancel_all()
                 ├─ cancel 后台 task
                 ├─ Player.kill()
                 └─ clear queue（clear_queue 默认 true）
              ← { ok, code, was_playing, cleared, message }
```

### 5.3 引擎降级

```
Router.speak(text):
  try:
      return await primary.synthesize_or_speak(text, timeout=edge_timeout)
  except (Timeout, EngineError):
      if fallback_enabled:
          return await fallback.speak(text)
      raise
```

- **Edge**：合成到临时文件 → Player 播放 → 播完删除（best-effort）。
- **SAPI**：优先 **子进程 PowerShell SAPI**，与可杀播放模型统一。

---

## 6. 核心抽象

### 6.1 数据模型（示意）

```python
class SpeakCategory(str, Enum):
    progress = "progress"
    error = "error"
    decision = "decision"
    summary = "summary"

@dataclass
class SpeakRequest:
    text: str
    priority: Literal["normal", "high"] = "normal"
    category: SpeakCategory = SpeakCategory.progress
    interrupt: bool = False

@dataclass
class SpeakResult:
    ok: bool
    code: str                 # OK | DISABLED | INVALID_TEXT | ...
    engine: str | None        # 受理路径推荐 null；实际引擎写日志
    queued: bool
    message: str

@dataclass
class StopResult:
    ok: bool
    code: str                 # OK | NOT_PLAYING | INTERNAL_ERROR
    was_playing: bool
    cleared: bool
    message: str
```

### 6.2 引擎接口

```python
class TtsEngine(Protocol):
    name: str
    async def speak(self, text: str, *, voice: str, rate: str) -> EngineOutcome:
        ...

class EngineOutcome(BaseModel):
    mode: Literal["direct", "file"]
    path: str | None = None  # mode=file
```

- `EdgeTtsEngine` → `mode=file`
- `SapiEngine` → `mode=direct`（或子进程 direct）

### 6.3 编排器状态机（P0）

```
Idle ──speak──► Playing
Playing ──speak(no interrupt)──► Playing + WaitingQueue(≤queue_size)
Playing ──speak(interrupt)──► Kill + ClearQueue → Playing(new)
* ──stop──► Idle（默认清空等待队列）
WaitingQueue 非空且 Playing 结束 ──► Playing(next)
```

- 并发：**正在播放最多 1 路**
- 等待队列容量：`queue_size`（默认 **3**，不含正在播）
- 溢出策略：丢弃等待队列中最旧并记日志，保证最新进展可听

### 6.4 去重（轻量）

对「`normalize(text)` + category」在短时间窗（默认 5s）内相同则跳过。

`normalize`（与契约一致）：

1. trim 首尾空白  
2. 连续空白折叠为单个空格  
3. 不做大小写折叠  

---

## 7. 配置设计

### 7.1 `config/default.yaml`（示意）

```yaml
tts:
  enabled: true
  max_chars: 80
  queue_size: 3
  dedupe_window_ms: 5000
  rate: "+0%"
  engine:
    primary: edge-tts
    fallback: sapi
    fallback_enabled: true
  edge:
    timeout_ms: 8000
    voice: "zh-CN-XiaoxiaoNeural"
  sapi:
    voice: ""
  playback:
    backend: auto   # auto | powershell | ffplay
  log_level: INFO
```

### 7.2 环境变量覆盖

| 环境变量 | 对应配置 |
|----------|----------|
| `CURSOR_TTS_ENABLED` | `tts.enabled` |
| `CURSOR_TTS_EDGE_VOICE` | `tts.edge.voice` |
| `CURSOR_TTS_SAPI_VOICE` | `tts.sapi.voice` |
| `CURSOR_TTS_MAX_CHARS` | `tts.max_chars` |
| `CURSOR_TTS_EDGE_TIMEOUT_MS` | `tts.edge.timeout_ms` |
| `CURSOR_TTS_FALLBACK` | `tts.engine.fallback_enabled` |

优先级：**环境变量 > `config/local.yaml`（可选）> `config/default.yaml`**。  
P0 可不提供 `local.yaml`。详见 [接入说明](../guide/Cursor接入与配置说明.md)。

### 7.3 Cursor MCP 注册（示意）

```json
{
  "mcpServers": {
    "cursor-tts": {
      "command": "python",
      "args": ["-m", "cursor_tts_mcp"],
      "cwd": "E:/WorkSpace/mcp",
      "env": {
        "CURSOR_TTS_ENABLED": "true"
      }
    }
  }
}
```

---

## 8. 并发、可靠性与错误处理

### 8.1 并发模型

- 主事件循环：MCP I/O
- 单一 `Orchestrator`：`asyncio.Lock` 保护队列与当前播放句柄
- 同时只允许 **一个** 播放子进程

### 8.2 错误分类

| 错误 | MCP 返回 | 进程 |
|------|----------|------|
| 空文本 / 超长 | `ok=false` + `code` | 不崩 |
| edge 超时后降级成功 | 工具响应通常已是 `OK`（`engine=null`）；**stderr 日志**记 `engine=sapi` | 不崩 |
| 双引擎失败 | 受理后通常已返回 OK；失败记 **stderr**（罕见同步失败才 ok=false） | 不崩 |
| 播放器拉起失败 | 受理后记 **stderr** | 不崩 |
| 未捕获异常 | stderr 日志 + 工具错误信息 | 尽量存活 |

### 8.3 临时文件

- 目录：系统临时目录下 `cursor-tts-mcp/`
- 生命周期：播放结束或 `stop` 后删除；启动时清理残留

### 8.4 资源泄漏防护

- `stop` 与进程退出 hook 统一走 `cancel_all()`
- 子进程设置守护超时，极端情况强制 kill

---

## 9. P0 → P1 演进

### 9.1 稳定契约（不要改）

- 工具名：`speak` / `stop`
- 入参语义：`text` / `priority` / `category` / `interrupt`
- 「受理后尽快返回」的行为

### 9.2 迁移步骤

1. 将 `orchestrator + engines + playback` 抽成 `tts_service` 包
2. 本机 HTTP（推荐 `127.0.0.1:18765`，可配）：
   - `POST /v1/speak`
   - `POST /v1/stop`
   - `GET /v1/health`
3. MCP `tools/*` 改为 HTTP 客户端
4. 队列加长（默认仍内存）
5. Hook：**仅当 Cursor Hooks 调研可行时**作为可选组件接入；默认关闭；不可用则跳过本步

### 9.3 兼容

- P0 配置键在 P1 复用；新增 `tts.service.url`
- Service 未启动时 MCP 返回明确错误，不回退半残单进程（避免双播放器）

---

## 10. 测试策略

| 层级 | 内容 |
|------|------|
| 单元 | `text_policy`、去重窗、队列溢出、router 降级（mock engine） |
| 组件 | orchestrator + fake player（记录 kill/play） |
| 手工 | Cursor 多步骤任务中间进展可听；`stop` 立刻停；断网测 SAPI |
| 非目标 P0 | 完整 CI 音频回归、云 TTS 合同测试 |

正式用例放 `tests/`；临时验证脚本用后删除。

---

## 11. 安全与隐私

- 仅处理短句状态文本；规则层禁止把源码/密钥拼进 `text`
- P1 端口绑定 `127.0.0.1`；开放 LAN 才需要 token（当前不做）
- 临时音频及时删除
- 日志可截断文案前 N 字，减少敏感信息落盘

---

## 12. 架构决策记录（ADR 摘要）

| ID | 决策 | 结论 |
|----|------|------|
| ADR-001 | 实现语言 | Python 3.11+ |
| ADR-002 | 传输 | MCP stdio |
| ADR-003 | 播放中断模型 | 子进程 + kill |
| ADR-004 | 返回时机 | 受理即返回，后台播放 |
| ADR-005 | 降级 | edge-tts → SAPI |
| ADR-006 | P1 拆分 | 本机 HTTP 服务，契约不变 |
| ADR-007 | Hook | P1 **调研后可选**，默认关；非必做 |

---

## 13. 实现顺序（对齐功能里程碑）

| 步骤 | 内容 | 对应 |
|------|------|------|
| T1 | 仓库骨架 + config + MCP `speak`/`stop` 空实现 | P0.1 |
| T2 | SAPI 引擎 + Player + Orchestrator 最短路径可听 | P0.1 |
| T3 | Edge 引擎 + 超时降级 | P0.2 |
| T4 | 短队列 / interrupt / 去重 | P0.2 |
| T5 | Cursor 接入说明 + User Rule + 进展触发验收 | P0.3 |
| T6 | 抽 Service + MCP 改客户端 | P1.1 |
| T7 | 日志字段增强；Hook 仅调研可行后可选 | P1.2 |

---

## 14. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-09-10 | 初稿：锁定 Python/MCP stdio；P0 单进程分层；P1 本机服务演进；进展触发下受理即返回与可杀播放 |
| v0.2 | 2026-09-10 | interrupt 清队列；edge/sapi 分音色；Hook 降为调研可选 |
| v0.3 | 2026-09-10 | SpeakResult/StopResult 对齐契约；queue_size/normalize 写死；文档树补全；SAPI 优先子进程 |
| v0.4 | 2026-09-10 | stderr 日志；local.yaml；§8.2 与响应 engine 字段解耦 |
