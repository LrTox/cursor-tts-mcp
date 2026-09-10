# MCP 工具契约说明（cursor-tts）

| 项 | 内容 |
|---|---|
| 版本 | v1.3 |
| 状态 | 实现合同（代码必须遵守） |
| 服务名 | `cursor-tts` |
| 传输 | MCP stdio（JSON-RPC） |
| 对应设计 | [功能设计](../design/TTS播报功能设计.md) / [技术架构](../design/TTS播报技术架构设计.md) |

> 本文是实现与联调的唯一工具合同。功能设计中的「建议」若与本文冲突，以本文为准。

---

## 1. 总则

### 1.1 工具清单

| 工具名 | 用途 |
|--------|------|
| `speak` | 受理一句短文本播报（进展/错误/决策/可选摘要） |
| `stop` | 立即停止当前播放并清空队列 |

P0/P1 **不得**增删改上述工具名；新增工具须另开契约版本。

### 1.2 行为总约束

1. **受理即返回**：`speak` 在校验通过并完成入队/投递后返回，**不得**等待播放结束再响应。
2. **进程不崩**：任何引擎/播放失败不得导致 MCP 进程退出。
3. **可中断**：`stop` 与 `speak(interrupt=true)` 必须能终止当前播放子进程。
4. **禁用默认全文朗读**：本契约不提供「朗读整段 Agent 回复」的工具或隐式行为。

### 1.3 内容返回约定

工具结果通过 MCP `CallToolResult` 返回：

- 业务成功/可预期失败：`isError=false`，`content` 中含 **一段 JSON 文本**（见各工具「响应体」）。
- 协议级异常（参数类型完全无法解析等）：可用 `isError=true`，但仍应尽量给出可读 `message`。

实现侧优先：**始终 `isError=false` + JSON 内 `ok` 字段表达业务成败**，便于 Agent 稳定解析。

---

## 2. 公共类型

### 2.1 Category

```text
"progress" | "error" | "decision" | "summary"
```

| 值 | 含义 |
|----|------|
| `progress` | 实质进展 |
| `error` | 阻塞/报错 |
| `decision` | 需用户决策 |
| `summary` | 收尾摘要（可选，不得作为唯一触发） |

### 2.2 Priority

```text
"normal" | "high"
```

P0：**仅接受并写日志，不参与调度**（description 中应注明，避免 Agent 误以为 high 会插队）。  
P1：可用于插队策略（可选增强）。

### 2.3 Engine 标识

```text
"edge-tts" | "sapi" | null
```

未实际选用引擎时（校验失败、去重跳过、总开关关闭）`engine` 为 `null`。

### 2.4 错误码 `code`

| code | 含义 | 典型场景 |
|------|------|----------|
| `OK` | 成功受理或成功停止 | — |
| `DISABLED` | 总开关关闭 | `tts.enabled=false` |
| `INVALID_TEXT` | 文本非法 | 空、纯空白 |
| `TEXT_TOO_LONG` | 超硬上限 | `len > max_chars` |
| `DEDUPED` | 短窗去重跳过 | 5s 内相同 text+category |
| `ENGINE_FAILED` | 主备引擎均失败 | **罕见/预留**：仅当实现选择在返回前同步探测且双失败时使用；正常「受理即返回」路径几乎不会出现 |
| `NOT_PLAYING` | 停止时无播放 | `stop` 时本来就空闲 |
| `INTERNAL_ERROR` | 未分类内部错误 | 应打日志 |

说明：

- `DEDUPED` 时 **`ok=true`，`code=DEDUPED`**，避免 Agent 重试刷屏。
- 播放在后台失败时：MCP 通常已返回 `OK`；失败仅记日志。不要求事后回调 Agent。
- 因此 **不要用同步响应里的 `engine`/`ENGINE_FAILED` 作为 P0 主引擎验收依据**；以日志为准。

---

## 3. 工具：`speak`

### 3.1 描述（给模型看的 description）

```text
播报一句简短中文状态。用于执行过程中的实质进展、报错或需要用户决策时。
不要朗读代码或长文。不要等整任务结束才调用。
```

### 3.2 入参 JSON Schema

```json
{
  "type": "object",
  "properties": {
    "text": {
      "type": "string",
      "minLength": 1,
      "description": "播报文案，简体中文短句"
    },
    "priority": {
      "type": "string",
      "enum": ["normal", "high"],
      "default": "normal",
      "description": "优先级；P0 仅记录不调度；error/decision 可用 high"
    },
    "category": {
      "type": "string",
      "enum": ["progress", "error", "decision", "summary"],
      "default": "progress",
      "description": "播报类别，用于日志与去重"
    },
    "interrupt": {
      "type": "boolean",
      "default": false,
      "description": "是否打断当前播放；错误场景建议 true"
    }
  },
  "required": ["text"],
  "additionalProperties": false
}
```

### 3.3 默认值与派生规则

| 条件 | 规则 |
|------|------|
| 未传 `priority` | `normal` |
| 未传 `category` | `progress` |
| 未传 `interrupt` | `false` |
| `category=error` 且未显式传 `interrupt` | **实现必须默认 `interrupt=true`** |
| `text` 首尾空白 | 先 trim；trim 后为空 → `INVALID_TEXT` |

### 3.4 文案硬约束

| 规则 | 值 |
|------|----|
| 计数方式 | Python `len(str)`，即 **Unicode 码点**（一个汉字计 1） |
| 硬上限 | `max_chars`（默认 **80**） |
| 超限策略 | **拒绝**（`TEXT_TOO_LONG`），**禁止截断后静默播放** |
| 建议长度 | ≤ 30（规则层约束，契约不强制） |
| Schema `minLength` | 空串可能在 MCP 参数校验层被拒，未进入 handler；业务上等价于失败，不一定落到 `INVALID_TEXT` |

### 3.5 `interrupt` 语义（写死）

当 `interrupt=true`（含 `category=error` 的默认派生）时，必须按下列顺序执行：

1. kill 当前播放子进程  
2. cancel 进行中的合成任务（best-effort）  
3. **清空待播队列**  
4. 再将本句作为唯一新任务投递/入队  

即：`interrupt=true` ≈ 「先等价做一次清队列的 stop，再播新句」。  
`interrupt=false`：不杀当前播放；若正在播则进入**等待队列**（等待最多 `queue_size`，默认 3，不含正在播）。

### 3.6 处理流程（实现必须遵守）

```
1. enabled? 否则返回 DISABLED
2. trim + 按 Unicode 码点校验 text 长度
3. 去重窗命中? 返回 DEDUPED（ok=true, queued=false）
4. interrupt=true? → kill 当前 + 清空队列
5. 入队或立即投递后台任务（正在播放最多 1 路 + 等待队列最多 queue_size，默认 3；等待溢出丢最旧）
6. 立即返回 OK（queued 标明是否在等播；engine 可为 null）
7. 后台：router(edge→sapi) → player；失败只记日志（含 engine 名）
```

**去重 `normalize(text)`（写死）**：

1. Unicode trim（去首尾空白）
2. 将连续空白（含空格/制表/换行）折叠为单个空格
3. **不做**大小写折叠（中文为主；英文保持原样）

去重键 = `normalize(text) + "\0" + category`。

### 3.7 响应体 Schema

```json
{
  "type": "object",
  "properties": {
    "ok": { "type": "boolean" },
    "code": {
      "type": "string",
      "enum": [
        "OK",
        "DISABLED",
        "INVALID_TEXT",
        "TEXT_TOO_LONG",
        "DEDUPED",
        "ENGINE_FAILED",
        "INTERNAL_ERROR"
      ]
    },
    "engine": {
      "anyOf": [
        { "type": "string", "enum": ["edge-tts", "sapi"] },
        { "type": "null" }
      ]
    },
    "queued": { "type": "boolean" },
    "message": { "type": "string" }
  },
  "required": ["ok", "code", "queued", "message"],
  "additionalProperties": false
}
```

注：受理即返回时，`engine` **推荐统一为 `null`**，实际选用引擎写入日志。字段必须存在。P0 不以响应中的 `engine` 作为验收依据。

### 3.8 示例

**成功受理**

```json
{
  "ok": true,
  "code": "OK",
  "engine": null,
  "queued": false,
  "message": "accepted"
}
```

**超长拒绝**

```json
{
  "ok": false,
  "code": "TEXT_TOO_LONG",
  "engine": null,
  "queued": false,
  "message": "text exceeds max_chars=80"
}
```

**去重**

```json
{
  "ok": true,
  "code": "DEDUPED",
  "engine": null,
  "queued": false,
  "message": "duplicate within dedupe window"
}
```

---

## 4. 工具：`stop`

### 4.1 描述

```text
立即停止当前语音播报。默认清空待播队列（clear_queue=true）；若 clear_queue=false 则只停当前、保留队列。
```

### 4.2 入参 JSON Schema

```json
{
  "type": "object",
  "properties": {
    "clear_queue": {
      "type": "boolean",
      "default": true,
      "description": "是否清空待播队列；默认 true"
    }
  },
  "additionalProperties": false
}
```

无参数调用合法（等同 `{}`）。

### 4.3 处理流程

```
1. 记录 was_playing / queue_size
2. kill 当前播放子进程
3. cancel 后台合成任务（best-effort）
4. clear_queue=true 则清空队列
5. 返回结果（空闲时 code=NOT_PLAYING 且 ok=true）
```

### 4.4 响应体 Schema

```json
{
  "type": "object",
  "properties": {
    "ok": { "type": "boolean" },
    "code": {
      "type": "string",
      "enum": ["OK", "NOT_PLAYING", "INTERNAL_ERROR"]
    },
    "was_playing": { "type": "boolean" },
    "cleared": { "type": "boolean" },
    "message": { "type": "string" }
  },
  "required": ["ok", "code", "was_playing", "cleared", "message"],
  "additionalProperties": false
}
```

### 4.5 示例

**停止成功**

```json
{
  "ok": true,
  "code": "OK",
  "was_playing": true,
  "cleared": true,
  "message": "stopped"
}
```

**本就空闲**

```json
{
  "ok": true,
  "code": "NOT_PLAYING",
  "was_playing": false,
  "cleared": true,
  "message": "nothing playing"
}
```

---

## 5. 非功能契约

| 项 | 要求 |
|----|------|
| `speak` P95 返回时延 | 校验+入队路径 < 200ms（不含合成播放）；**目标值，不作 P0 门禁** |
| 队列容量 | **正在播放最多 1 路 + 等待最多 `queue_size`（默认 3）**；等待溢出丢最旧 |
| 去重窗 | 默认 5000ms；键为 `normalize(text)+category`（normalize 见 §3.6） |
| 主引擎超时 | `edge.timeout_ms` 默认 8000 |
| 降级 | edge 失败/超时 → sapi（fallback_enabled=true） |
| 音色配置 | **分引擎**：`edge.voice` 与 `sapi.voice` 不得混用同一 Neural ID |
| 日志（P0） | 引擎名与失败原因输出到 **stderr**；级别由 `CURSOR_TTS_LOG_LEVEL` 控制 |
| 并发播放 | 同时最多 1 路 |

---

## 6. 版本与兼容

| 规则 | 说明 |
|------|------|
| 字段只增不改语义 | 新增可选字段须 bump 次版本 |
| 工具改名/删字段 | 须 bump 主版本并改本文 |
| P1 HTTP 服务 | 请求/响应字段与本文对齐，路径另见 P1 API 文档 |

---

## 7. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-10 | 首版实现合同：speak/stop Schema、错误码、默认 interrupt 规则 |
| v1.1 | 2026-09-10 | 写死 interrupt 清队列；Unicode 码点计数；voice 分引擎；priority/ENGINE_FAILED/engine 验收澄清 |
| v1.2 | 2026-09-10 | 写死 queue_size=等待上限；normalize 规则 |
| v1.3 | 2026-09-10 | stop description 对齐 clear_queue；P0 stderr 日志写入非功能契约 |
