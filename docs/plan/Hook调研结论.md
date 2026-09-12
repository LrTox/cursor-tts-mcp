# Hook 调研结论（T7）

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-11（修订 · 禁止只播开头结尾） |
| 结论 | **过程重要内容必播**；开头说过不算完；spoke 后若继续工具工作仍催促；Plan 同理 |
| 对应验收 | AC-P1-02/03 全文朗读仍 N/A |

## 根因（Cursor 平台行为）

Rules（含 `alwaysApply`）按**对话会话**装配，官方未承诺中途改 `.mdc` 会热更新。  
因此旧 Agent 对话普遍可能缺少后来新增的规则——不单 TTS。

Hooks 的 `hooks.json` **会监视并热重载**，可作为补丁通道。

**无法真正「热更新 Rules 全文」**；能做的是：用 Hook 把 speak 约束注入/催促到旧对话。

## 已落地修复

路径：

- `%USERPROFILE%\.cursor\hooks.json`
- `%USERPROFILE%\.cursor\hooks\tts_speak_remind.py`
- `%USERPROFILE%\.cursor\rules\cursor-tts-speak.mdc`（新对话）
- `mcp/.cursor/rules/cursor-tts-speak.mdc`（仓库副本）

| Hook | 对旧对话的作用 |
|------|----------------|
| `beforeSubmitPrompt` | 标记新一轮用户消息（清零本轮 speak 标记）；同步 payload 中的 plan/agent mode |
| `sessionStart` | 注入过程播报提醒（在解决什么 / 结果是什么；含 Plan 子任务） |
| `preToolUse` | Plan/Agent 均可 nudge（90s 节流） |
| `postToolUse` | Plan/Agent 均可注入提醒（60s 节流） |
| `afterMCPExecution` | 识别 speak 并记录 |
| `afterAgentResponse` | 整份计划稿不自动播；过程结论可兜底短句 |
| `subagentStop` | 子代理结束后催促过程/结果 speak（90s） |
| `stop` | 有工具活动却未 speak → followup |

### 2026-09-11 播报意图澄清

| 问题 | 修复 |
|------|------|
| 误做成「仅子任务开始/结束各一句」 | 改为子任务**执行过程中**播：在解决什么、结果是什么 |
| 「第 N 步」被当成规范 | 规则写明举例非格式；禁止机械念稿 |
| 工具级刷屏 | 仍禁止无信息量的每次工具成功播报 |

### 2026-09-10 热更新失败二次修复

| 问题 | 修复 |
|------|------|
| `postToolUse` matcher 过窄（仅 Task/Shell/Write/Grep…） | 去掉 matcher，脚本内节流 |
| `afterMCPExecution` matcher=`speak` 可能漏掉 CallDynamicTool | 去掉 matcher，按 payload 识别 speak |
| 旧对话缺少回合内提醒 | 新增 `preToolUse` → `agent_message` |

本地脚本自测：Plan 模式 stop/subagent 不催；Agent 有 speak 则 stop 不催；无 speak 且有工具活动则 stop 产出 `followup_message`。

## 局限

- Cursor **无法**让旧对话真正热加载全部 Rules 文本；本方案只保证 **TTS speak 约束**在旧对话可被催出。
- 纯闲聊、本轮零工具调用时，不强制 followup（避免打扰）。
- Plan mode 若 payload 不带 mode 字段，依赖 SwitchMode/CreatePlan 痕迹与文稿启发式，极端情况下需用户切回 Agent 后再播。
- 若 Hook 未生效：Cursor Settings → Hooks 查看；或 **Developer: Reload Window**。
- 全新对话仍以 User Rules / 项目 Rules 为准；Hook 是旧对话补丁与兜底。
