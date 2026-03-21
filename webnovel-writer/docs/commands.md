# 命令说明

## `webnovel init`

用途：初始化小说项目目录、基础模板和状态文件。

产出：

- `.webnovel/state.json`
- `.webnovel/planning-profile.json`
- `设定集/`
- `大纲/总纲.md`

说明：

- 初始化会同时写入首轮 `plan` 可消费的最小 planning profile 和更完整的总纲骨架。
- 推荐在 Dashboard 的 `Planning Profile` 中先确认并保存这些字段，再执行 `webnovel plan 1`。

## `webnovel plan [卷号]`

用途：生成卷级规划与节拍。

示例：

```powershell
webnovel plan 1
webnovel plan 2-3
```

说明：

- `plan` 在进入模型规划前会先做本地预检，合并读取 `.webnovel/planning-profile.json`、`.webnovel/state.json` 中的 `planning.project_info` 与 `大纲/总纲.md`。
- 如果输入不足，任务会以 `failed` 结束，错误码固定为 `PLAN_INPUT_BLOCKED`，并在 `details.blocking_items` 中返回缺失项。
- `PLAN_INPUT_BLOCKED` 时不会生成或覆盖空壳卷规划文件。

## `webnovel write [章号]`

用途：执行完整章节创作流水线。

示例：

```powershell
webnovel write 1
webnovel write 45
```

常见模式：

- 标准模式：全流程。
- 快速模式：`--fast`
- 极简模式：`--minimal`

## `webnovel review [范围]`

用途：对历史章节做多维质量审查。

示例：

```powershell
webnovel review 1-5
webnovel review 45
```

说明：

- review 汇总结果现在会结构化返回 `repair_candidates[]`。
- 命中自动修稿白名单的问题可以直接发起 `repair` 任务；未命中白名单的问题仍需人工处理。

## `webnovel repair [章号]`

用途：针对单章已识别内容问题执行局部自动修稿，并在复审通过后写回正文。

适用问题类型：

- `AMBIGUOUS_WARNING_SOURCE`
- `RULE_SCOPE_CONFUSION`
- `TRANSITION_CLARITY`
- `HOOK_BRIDGE_GAP`
- `PLOT_THREAD_CONTINUITY`
- `MEMORY_LOSS_OBJECTIVITY`

说明：

- `repair` 默认不走人工审批；如果请求显式传入 `require_manual_approval = true`，任务会在 `approval-gate` 停下，等待批准后再写回。
- 完整流程为 `repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`。
- 只有复审通过后才会写回正文；若复审仍阻断，任务会以 `REPAIR_REVIEW_BLOCKED` 失败。
- 成功写回时会同时生成章节备份与 repair report，目录分别位于 `.webnovel/repair-backups/` 和 `.webnovel/repair-reports/`。

## `webnovel query [关键词]`

用途：查询角色、伏笔、节奏、状态等运行时信息。

示例：

```powershell
webnovel query 萧炎
webnovel query 伏笔
webnovel query 紧急
```

## `webnovel resume`

用途：任务中断后自动识别断点并恢复。

示例：

```powershell
webnovel resume
```

## Dashboard Frontend Verification

When `dashboard/frontend/src/` changes, run:

```powershell
Set-Location .\dashboard\frontend
npm run build
```

Commit the regenerated `dashboard/frontend/dist/` in the same change, and keep only the latest hashed files under `dist/assets/`.
