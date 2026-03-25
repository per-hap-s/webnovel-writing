# 系统架构与当前实现

## 单一真源

当前写作主链以 `webnovel-writer/workflow_specs/write.json` 为唯一真源。

当前真实步骤固定为：

`story-director -> chapter-director -> chapter-brief-approval -> context -> draft -> consistency-review -> continuity-review -> ooc-review -> review-summary -> polish -> approval-gate -> data-sync`

约束：

- 当前版本不实现 `subtask`、自动路由（auto route，自动分流）或 6-checker（六审查器）动态插拔。
- 审查器固定为 3 个：`consistency-review`、`continuity-review`、`ooc-review`。
- `context`、3 个 review step（审查步骤）、`polish`、`data-sync` 都受严格输出合同约束。

## 运行结构

系统由 4 层组成：

1. Dashboard（控制台）与前端任务中心，负责展示任务状态、审批、继续建议和操作入口。
2. `dashboard/orchestrator.py`，负责调度工作流、执行步骤、处理审批闸门和恢复逻辑。
3. `dashboard/task_store.py`，负责任务文件、事件日志、运行态元数据的持久化。
4. `.webnovel` 状态与索引层，负责章节正文、摘要、`state.json`、索引数据库等长期数据。

## 写作链路状态机

### 写作任务

- 默认先执行 `story-director` 和 `chapter-director`。
- 任务必须先停在 `chapter-brief-approval`，等待人工确认章节 brief（章节简报）。
- brief 批准后才进入 `context -> draft -> 3 个审查 -> review-summary -> polish`。
- 只有请求显式带上 `require_manual_approval = true` 时，任务才会在 `approval-gate` 再次停下等待回写审批。
- `data-sync` 负责正文、摘要、项目状态和索引同步。

### 修稿任务

修稿链路固定为：

`repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`

说明：

- 修稿默认直接回写。
- 只有请求显式带上 `require_manual_approval = true` 时，才会停在 `approval-gate`。

## 审批与恢复闸门

后端以状态为准，不信任外部随意指定恢复点：

- `awaiting_chapter_brief_approval` 只能从 `chapter-brief-approval` 恢复。
- `awaiting_writeback_approval` 的写作任务只能从 `approval-gate` 恢复。
- `awaiting_writeback_approval` 的修稿任务只能从 `repair-writeback` 恢复。
- `approve_writeback()` 只接受两种等待审批状态：
  - `awaiting_chapter_brief_approval`
  - `awaiting_writeback_approval`

## 严格输出合同

当前关键步骤必须满足这些最小字段：

- `context`：
  - `story_plan`
  - `director_brief`
  - `task_brief`
  - `contract_v2`
  - `draft_prompt`
- `consistency-review` / `continuity-review` / `ooc-review`：
  - `agent`
  - `chapter`
  - `overall_score`
  - `pass`
  - `issues`
  - `metrics`
  - `summary`

`review-summary` 会继续汇总并落库 `review_metrics`，但前提是上游审查输出已经满足完整合同。

## 持久化一致性

`dashboard/task_store.py` 使用任务文件 + 事件 JSONL（JSON Lines，逐行 JSON）持久化运行状态。

当前约束：

- 事件日志继续追加到 `*.events.jsonl`。
- 任务主文件的状态迁移必须走锁内 read-modify-write（读改写）。
- `update_task`、`save_step_result`、`mark_waiting_for_approval`、`reset_for_retry`、`prepare_for_resume` 等写路径都必须在文件锁内重新读取最新任务，再原子写回。

## 前端状态判定

前端任务中心只根据强证据给结论，不根据兜底文案猜测状态：

- `approval_status = pending` 或任务状态本身属于审批态时，顶部运行态显示“待审批”。
- 普通 `write` 任务只要 `review_summary.blocking = true`，就不能显示“可继续下一章”。
- `story_alignment.missed` 或 `director_alignment.missed` 非空时，默认降级为“未达继续条件，需人工复核”。
- 继续结论与可点击的 `operatorActions` 必须同屏一致。

## Shell 约束

Windows 默认 shell（命令行）按 `PowerShell` 执行。文档、skill 和示例命令都应使用可直接在 `PowerShell` 中运行的语法，不混用 `bash/sh` 写法。

## LLM fallback（模型自动降级）执行语义

`dashboard/llm_runner.py` 中的 `OpenAICompatibleRunner` 现在把 API 模式下的写作步骤分成两段尝试：

1. primary model（默认模型）阶段：继续沿用现有 `_max_retries_for_step()` 和 `_timeout_seconds_for_step()`。
2. fallback model（回退模型）阶段：仅在 primary 阶段耗尽且错误属于 `LLM_TIMEOUT` 或可重试 `5xx` `LLM_HTTP_ERROR` 时，追加一次 `gpt-5.4-mini` 尝试。

当前默认策略：

- `WEBNOVEL_LLM_ENABLE_FALLBACK=true`
- `WEBNOVEL_LLM_FALLBACK_MODEL=gpt-5.4-mini`
- `WEBNOVEL_LLM_FALLBACK_STEPS=draft,polish`
- `WEBNOVEL_LLM_FALLBACK_ON=LLM_TIMEOUT,LLM_HTTP_ERROR`

对外约束：

- `4xx`、配置错误、解析错误、`INVALID_STEP_OUTPUT` 不触发 fallback
- `StepResult.metadata` 会暴露 `effective_model`、`primary_model`、`fallback_model`、`fallback_used`、`attempt_models`
- 最终失败对象会额外暴露 `fallback_used`、`effective_model`、`fallback_exhausted`
- `OrchestrationService` 会把 `llm_fallback_scheduled` / `started` / `succeeded` / `failed` 写入事件流，并同步到 `runtime_status`
