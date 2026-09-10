# Hook 调研结论（T7）

| 项 | 内容 |
|---|---|
| 日期 | 2026-09-10（修订 · 热更新补丁加固） |
| 结论 | **不做自动全文朗读**；用用户级 Hook **修复旧对话不吃 Rules** |
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
- `cqca-lms/.cursor/rules/cursor-tts-speak.mdc`（LMS 项目副本）

| Hook | 对旧对话的作用 |
|------|----------------|
| `beforeSubmitPrompt` | 标记新一轮用户消息（清零本轮 speak 标记）；**不能**注入 context（平台 schema 限制） |
| `sessionStart` | 新对话注入强制 speak 上下文 |
| `preToolUse` | 任意工具前注入 `agent_message` 催促（90s 节流）；标记本轮有工具活动 |
| `postToolUse` | **无 matcher**，覆盖 Read/StrReplace/CallDynamicTool 等；工具后注入提醒（45s 节流） |
| `afterMCPExecution` | **无 matcher**；识别 speak（含 CallDynamicTool→speak）并记录本轮已 speak |
| `subagentStop` | 子代理结束后 followup 催促 speak |
| `stop` | 本轮用过工具却未 speak → 自动 followup 再催一次（`loop_limit=1`） |

### 2026-09-10 热更新失败二次修复

| 问题 | 修复 |
|------|------|
| `postToolUse` matcher 过窄（仅 Task/Shell/Write/Grep…） | 去掉 matcher，脚本内节流 |
| `afterMCPExecution` matcher=`speak` 可能漏掉 CallDynamicTool | 去掉 matcher，按 payload 识别 speak |
| 旧对话缺少回合内提醒 | 新增 `preToolUse` → `agent_message` |

本地脚本自测：有 speak 则 stop 不催；无 speak 且有工具活动则 stop 产出 `followup_message`；Read 类工具也会标记 tools。

## 局限

- Cursor **无法**让旧对话真正热加载全部 Rules 文本；本方案只保证 **TTS speak 约束**在旧对话可被催出。
- 纯闲聊、本轮零工具调用时，不强制 followup（避免打扰）。
- 若 Hook 未生效：Cursor Settings → Hooks 查看；或 **Developer: Reload Window**。
- 全新对话仍以 User Rules / 项目 Rules 为准；Hook 是旧对话补丁与兜底。
