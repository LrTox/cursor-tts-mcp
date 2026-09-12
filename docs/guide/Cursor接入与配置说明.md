# Cursor 接入与配置说明

| 项 | 内容 |
|---|---|
| 版本 | v1.4 |
| 状态 | 实现/联调规范 |
| 适用 | P0（单进程 MCP） |
| 关联 | [MCP工具契约](../spec/MCP工具契约.md) / [技术架构](../design/TTS播报技术架构设计.md) / [P1服务API](../spec/P1服务API.md) |


---

## 1. 前置条件

| 项 | 要求 |
|----|------|
| OS | Windows 10+ |
| Python | 3.11+（`python --version` 可验证） |
| 网络 | 使用 edge-tts 时需要能访问微软语音服务；仅 SAPI 时可离线 |
| Cursor | 支持 MCP Servers 配置的版本 |

---

## 2. 安装依赖（实现就绪后）

在仓库根目录：

```powershell
cd E:\WorkSpace\mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

（具体包名以 `pyproject.toml` 为准；未生成代码前本章作为目标流程。）

可选自检：

```powershell
python -m cursor_tts_mcp --help
# 或直接由 Cursor 拉起 stdio，无需手动常驻
```

---

## 3. MCP 注册

### 3.1 推荐配置（本仓库已提供）

**注意：`cursor-tts` 请只在一处注册**（用户 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`），两处同时注册会导致 MCP 一直 loading。

当前推荐写在用户配置（与 playwright 一起），项目 `.cursor/mcp.json` 留空以免重复。

若 Cursor 未自动加载项目 MCP，可手动合并到用户 MCP 配置（路径按本机修改）：

```json
{
  "mcpServers": {
    "cursor-tts": {
      "command": "E:/WorkSpace/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "cursor_tts_mcp"],
      "cwd": "E:/WorkSpace/mcp",
      "env": {
        "CURSOR_TTS_ENABLED": "true",
        "CURSOR_TTS_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

说明：

- 优先使用 **venv 内 python**，避免系统解释器缺依赖。
- `cwd` 指向仓库根，便于加载 `config/default.yaml`。
- 服务名固定为 **`cursor-tts`**，与契约一致。
- **P1 默认 http 模式**：MCP 为薄客户端；若 `127.0.0.1:18765` 未就绪且 `autostart=true`，会自动执行 `python -m tts_service`。详见 [P1服务API](../spec/P1服务API.md)。
- 单测/应急可设 `CURSOR_TTS_MODE=embedded`（本进程播放，勿与 http 服务同时播）。

### 3.2 注册后检查

1. Cursor MCP 面板中 `cursor-tts` 为已连接/无报错。
2. 工具列表可见 `speak`、`stop`。
3. 手动让 Agent 调用：`speak`，文案「接入测试成功」，应能出声。

---

## 4. 配置项

### 4.1 优先级

**环境变量 > 用户配置文件 > `config/default.yaml`**

| 层级 | P0 约定 |
|------|--------|
| 环境变量 | 见下表；MCP 注册里的 `env` 最常用 |
| 用户配置文件 | 可选：仓库根下 `config/local.yaml`（若存在则加载；**勿提交密钥**；可加入 `.gitignore`） |
| 默认配置 | 始终加载 `config/default.yaml` |

P0 允许只使用「环境变量 + default.yaml」，不创建 `local.yaml`。

### 4.2 默认配置（目标文件 `config/default.yaml`）

```yaml
tts:
  enabled: true
  max_chars: 80
  queue_size: 3
  dedupe_window_ms: 5000
  rate: "+0%"                 # 主要用于 edge-tts；SAPI 可忽略
  engine:
    primary: edge-tts
    fallback: sapi
    fallback_enabled: true
  edge:
    timeout_ms: 8000
    voice: "zh-CN-XiaoxiaoNeural"
  sapi:
    voice: ""          # 空=系统默认中文音；勿填 Neural 音色 ID
  playback:
    backend: auto
  log_level: INFO
```

说明：`edge.voice` 与 `sapi.voice` **必须分开**；不得把 `zh-CN-*-Neural` 传给 SAPI。

### 4.3 环境变量

| 环境变量 | 含义 | 示例 |
|----------|------|------|
| `CURSOR_TTS_ENABLED` | 总开关 | `true` / `false` |
| `CURSOR_TTS_EDGE_VOICE` | edge-tts 音色；`auto`=跟系统语言 | `auto` / `zh-CN-XiaoxiaoNeural` |
| `CURSOR_TTS_LOCALE_AUTO` | 是否按系统 UI 语言选音色 | `true` / `false` |
| `CURSOR_TTS_FORCE_LOCALE` | 强制语言标签（调试用） | `en-US` / `zh-CN` |
| `CURSOR_TTS_SAPI_VOICE` | SAPI 音色名（可空） | `Microsoft Huihui Desktop` |
| `CURSOR_TTS_MAX_CHARS` | 文案硬上限（Unicode 码点） | `80` |
| `CURSOR_TTS_EDGE_TIMEOUT_MS` | edge 超时 | `8000` |
| `CURSOR_TTS_FALLBACK` | 是否启用引擎兜底（默认关，避免 SAPI 机械音） | `true` / `false` |
| `CURSOR_TTS_ALLOW_SAPI` | 是否允许使用 SAPI（主引擎或兜底；默认关） | `true` / `false` |
| `CURSOR_TTS_EXCLUSIVE_PLAYBACK` | 跨进程互斥，避免叠播 | `true` / `false` |

### 用户级规则（全局播报）

强制调用 `speak` 的规则已安装到用户级：

`C:\Users\17695\.cursor\rules\cursor-tts-speak.mdc`（`alwaysApply: true`）

这样在 **LMS 等任意工作区**也会要求 Agent 播报。项目内 `mcp/.cursor/rules/` 可保留作仓库副本。  
**新开 Agent 对话**后规则更稳妥生效。

### 旧对话不触发的原因与修复

Cursor **Rules 通常不会在已打开的旧对话中热更新**（按会话装配）；重连 MCP 也不重载规则。  
因此已在用户级安装 **Hooks 提醒**（会热重载）：

- `%USERPROFILE%\.cursor\hooks.json`
- `%USERPROFILE%\.cursor\hooks\tts_speak_remind.py`

在旧对话里：催促过程播报（在解决什么 / 结果是什么）；**Plan 子任务执行中同样播**；不朗读整份计划。详见 [Hook调研结论](../plan/Hook调研结论.md)。

| `CURSOR_TTS_LOG_LEVEL` | 日志级别 | `INFO` |

### 4.4 常用场景

| 场景 | 配置 |
|------|------|
| 临时静音 | `CURSOR_TTS_ENABLED=false` |
| 关掉兜底（仅测 edge，**推荐听感**） | `CURSOR_TTS_FALLBACK=false` + `CURSOR_TTS_ALLOW_SAPI=false`（默认） |
| 强制启用 SAPI（仅排查） | `CURSOR_TTS_ALLOW_SAPI=true` 且按需 `CURSOR_TTS_FALLBACK=true` 或 `primary: sapi` |

---

## 5. User Rule（定稿）

项目规则文件（推荐）：`.cursor/rules/cursor-tts-speak.mdc`（已写入，alwaysApply）。  
**以该文件为准**；下面为摘要。

### 必须 `speak` 的时机

| 时机 | category |
|------|----------|
| 开始解决某个问题 / 进入一段工作 | `progress` |
| 该段有结果 / 发现 | `progress` / `summary` |
| **任务结果 / 结论交付**（必说） | `summary` |
| 报错 / 阻塞 | `error` + `interrupt=true` |
| 需要用户决策 / 确认 / 操作 | `decision` |

Plan 子任务执行过程中同样适用上表（过程细节要可听）。

### 不要 `speak`

无信息量的工具成功；每个小文件读写；朗读代码/日志/长文/整份计划稿；把举例话术当强制格式念稿。

也可粘贴到 Cursor User Rules：

```text
【语音播报 cursor-tts】
1. 执行中（含 Plan 子任务过程）speak：正在解决什么、得到什么结果。
2. 举例不是格式规范；不要机械念「第 N 步」。
3. 禁止每个工具都说；禁止朗读计划全文；禁止只打字。
4. 参数：进展 progress；报错 error+interrupt；决策 decision；结果 summary。
5. 用户要安静时调用 stop。
```

### 5.1 反例（禁止）

- 子任务执行半天完全不说话
- 每个 Read 都说「读文件成功」
- 把「第一步/第二步」举例当成必须念的脚本
- `speak` 传入整段计划或长报告

### 5.2 正例（意图示例，非固定句式）

- 「在查生产 RCS 模板号」
- 「查到生产走中力，模板仍是 F 系列」
- 「交管点映射对上了，差在车辆分组」
- 「有两种方案，请你选择」

---

## 6. 联调自检清单

按顺序执行，全部通过再进入功能验收：

| # | 步骤 | 期望 |
|---|------|------|
| 1 | MCP 显示已连接 | 无启动错误 |
| 2 | 工具列表含 speak/stop | 名称一致 |
| 3 | `speak`「自检一句」 | 能听到声音 |
| 4 | 播报中途 `stop` | 声音立即停 |
| 5 | 连续两次相同短句（5s 内） | 第二次 `DEDUPED` 或不明感重复刷屏 |
| 6 | `text` 超过 80 个 Unicode 码点 | 返回 `TEXT_TOO_LONG`，不出声 |
| 7 | 断网或关闭 fallback 测失败路径 | 进程不崩；有兜底则 SAPI 可听 |
| 8 | 多步骤任务（见验收用例） | **中间进展点**有播报 |

---

## 7. 日志与排障速查

### 7.1 日志约定（P0 必做）

| 项 | 约定 |
|----|------|
| 输出位置 | **进程 stderr**（Cursor MCP 面板/日志中可见） |
| 级别 | `CURSOR_TTS_LOG_LEVEL`（默认 `INFO`） |
| P0 必打字段 | 选用引擎名（`edge-tts` / `sapi`）、失败原因（若有）、stop/kill 事件 |
| P1 增强 | 再补 `category`、更完整结构化字段（见验收 AC-P1-04） |

验收 AC-FB-01/02 **以 stderr 日志中的引擎名为准**，不以工具响应里的 `engine` 字段为准。

### 7.2 排障速查

| 现象 | 排查 |
|------|------|
| 工具不出现 | MCP JSON 路径/python 是否正确；重启 Cursor |
| 有返回无声音 | 系统音量；播放后端；stderr 是否 ENGINE 失败 |
| 仅结束才说话 | User Rule 未生效或被其它规则覆盖 |
| edge 很慢/失败 | 网络；超时；确认 fallback 开启 |
| stop 不停 | 确认杀的是播放子进程；查是否多实例 MCP |

级别调到 `DEBUG` 可定位播放 PID 与队列状态。

---

## 8. 安全注意

- 不要把密钥、Token、整文件内容传入 `text`。
- 不要把 MCP 改成监听非本机地址（P1 亦仅 `127.0.0.1`）。
- `config/local.yaml` 若含本机路径/偏好，勿提交敏感内容。

---

## 9. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-10 | 首版：注册、配置、User Rule 定稿、自检与排障 |
| v1.1 | 2026-09-10 | edge/sapi 音色拆分；环境变量更名 |
| v1.2 | 2026-09-10 | 排版微调；与契约 v1.2 配置语义对齐 |
| v1.3 | 2026-09-10 | 用户配置路径 `config/local.yaml`；P0 stderr 日志约定；码点措辞 |
| v1.4 | 2026-09-10 | 补充 `.cursor/mcp.json` 与项目 Rule 路径 |