# 多子代理测试协调器（仓库级验证入口）

## 定位

这是仓库级 verification coordinator（验证协调器），不是产品功能入口。它固定采用“两阶段”执行：

1. 本地 lanes（验证通道）并行：
   - `backend`
   - `data-cli`
   - `frontend`
2. 只有本地结果没有形成高优先级阻断时，才串行复用既有 RealE2E（真实全链路实测）。

正式入口：

```powershell
& '.\tools\Tests\Run-Webnovel-MultiAgentTest.ps1'
```

默认产物根目录：

```text
output/verification/multi-agent-test/YYYYMMDD-runid/
```

## 执行流程

1. 先跑 `preflight`（预检），分成静态存在性检查和轻量可用性检查。
2. 并行执行 `backend`、`data-cli`、`frontend` 三个 lane。
3. 每个 lane 内按 step（步骤）顺序执行；每个 step 都有固定 `blocking_severity`（阻断严重度）和 `timeout_seconds`（超时秒数）。
4. 每个 step 使用独立进程执行，并把 `stdout`、`stderr`、combined log（合并日志）写入 `lane-logs/`。
5. 本地汇总使用显式规则决定是否继续 RealE2E：
   - 任一失败 step 的 `failure_kind = environment` -> `environment_blocked`
   - 任一失败 step 的 `blocking_severity = blocking` -> `local_blocker`
   - 只有 `non_blocking` step 失败 -> `local_regression`
   - 全部通过 -> `pass`
6. 只有 `pass` 或 `local_regression` 才继续 RealE2E。

## Preflight Contract

`preflight.json` 固定返回：

- `classification`: `pass` 或 `environment_blocked`
- `ready`
- `checked_at`
- `checks[]`
- `issues[]`
- `missing_paths[]`
- `failed_commands[]`

静态存在性检查固定覆盖：

- `python`
- `node`
- `npm`
- `npx`
- `tools/Webnovel-RealE2E.psm1`
- Playwright 脚本
- `dashboard/frontend/node_modules`

轻量可用性检查固定覆盖：

- `python -m pytest --version`
- `node --version`
- `npm --version`
- `npx --version`

预检不会启动浏览器，不会调用在线 API，也不会提前运行 RealE2E。

## Lane Contract

当前固定 lane / step 如下：

- `backend.dashboard-root-contract`
  `blocking_severity = blocking`
  `timeout_seconds = 600`
- `backend.dashboard-package-contract`
  `blocking_severity = blocking`
  `timeout_seconds = 900`
- `data-cli.state-and-cli-contracts`
  `blocking_severity = blocking`
  `timeout_seconds = 900`
- `data-cli.mock-cli-e2e`
  `blocking_severity = non_blocking`
  `timeout_seconds = 600`
- `frontend.frontend-tests`
  `blocking_severity = blocking`
  `timeout_seconds = 900`
- `frontend.frontend-typecheck`
  `blocking_severity = non_blocking`
  `timeout_seconds = 600`

每个 lane JSON 固定包含：

- `name`
- `status`
- `failed_step_count`
- `suspected_environment_issue`
- `failed_step_names[]`
- `blocking_step_names[]`
- `recommended_action`
- `steps[]`

每个 step 固定包含：

- `id`
- `name`
- `passed`
- `exit_code`
- `failure_kind`
- `blocking_severity`
- `timed_out`
- `timeout_seconds`
- `stdout_log_path`
- `stderr_log_path`
- `combined_log_path`
- `excerpt`

## Failure Kind

`failure_kind`（失败类型）按固定顺序判定：

1. `timeout`
2. `environment`
3. `test_failure`
4. `tooling_failure`

说明：

- `environment` 用于缺命令、缺模块、缺路径、导入失败、`ENOENT`、`Missing script` 等环境缺失。
- `test_failure` 表示测试真正启动并执行到了断言失败。
- `tooling_failure` 表示命令本身异常退出，但不属于明确环境缺失。
- `timeout` 会直接保留为 step 级失败类型，并通过日志定位。

## Result Contract

`result.json` 固定包含：

- `classification`
- `passed`
- `preflight`
- `lanes`
- `local_decision`
- `real_e2e`
- `blocking_step_ids[]`
- `next_action`
- `failure_summary`
- `minimal_repro`
- `failure_fingerprint`
- `manifest`

`next_action` 目前使用稳定 action code（动作码），不是自由文本：

- `fix_environment_first`
- `fix_local_blocker_and_rerun`
- `fix_non_blocking_local_regressions`
- `repair_mainline_product_flow`
- `repair_regressed_pages`
- `repair_readonly_audit_failures`
- `rerun_after_cancel`
- `ready_to_pass`

`classification` 现在除了原有的 `environment_blocked` / `local_blocker` / `local_regression` / `mainline_failure` / `page_regression` / `readonly_audit_failure` / `pass` 之外，还支持 `cancelled`。

`report.md` 固定输出：

- `Preflight`
- `Local Lanes`
- `RealE2E`
- `Verdict`

并展示首个失败 step、失败类型、阻断级别、日志路径、最终 action code（动作码）和失败摘要。

## Runtime Contract

协调器现在会把运行态和控制文件落在标准产物目录中，供 Dashboard（仪表盘）恢复运行态、轮询进度和发出停止请求：

- `output/verification/multi-agent-test/_runtime/active-execution.json`
- `output/verification/multi-agent-test/_runtime/last-known.json`
- `{run_id}/progress.json`
- `{run_id}/control.json`
- `{run_id}/manifest.json`

其中：

- `progress.json` 固定包含：
  - `run_id`
  - `status`
  - `phase`
  - `current_lane`
  - `current_step_id`
  - `current_step_name`
  - `completed_steps`
  - `total_steps`
  - `started_at`
  - `updated_at`
  - `last_completed_step_id`
  - `real_e2e_status`
- `control.json` 目前只用于优雅停止，固定写入：
  - `stop_requested`
  - `requested_at`
- `manifest.json` 是给 Dashboard 与未来 headless（无头）自动化复用的稳定机器契约，至少包含：
  - `manifest_version`
  - `run_id`
  - `classification`
  - `next_action`
  - `failure_fingerprint`
  - `artifact_paths`

停止语义：

- Dashboard 不会先直接强杀顶层 PowerShell（PowerShell）进程。
- `POST /api/workbench/verification/run/stop` 先写 `control.json` 请求协调器在安全检查点退出。
- 若 10 秒后仍未退出，Dashboard 才会执行 `Stop-Process -Force`，执行态会短暂记成 `cancelled_force_killed`，但 run 级 `classification` 仍统一归类为 `cancelled`。

## Minimal Repro And Fingerprint

`minimal_repro`（最小复现）和 `failure_fingerprint`（失败指纹）已经变成稳定字段：

- `environment_blocked`：优先给出缺失命令、缺失路径或失败的版本探针。
- `local_blocker` / `local_regression`：优先给出首个失败 step 的正式命令。
- `mainline_failure` / `page_regression` / `readonly_audit_failure`：优先给出正式 `Run-Webnovel-RealE2E.ps1` 入口和关键产物路径。
- `cancelled`：最小复现为正式协调器入口，动作码固定为 `rerun_after_cancel`。

`failure_fingerprint` 生成规则固定为：

- 环境问题：缺失项集合
- 本地失败：`step_id + failure_kind`
- RealE2E 失败：`classification + first failing page/task`
- 已取消：固定为 `cancelled`

## RealE2E 复用边界

协调器不会改写 RealE2E 自身协议，只决定“是否调用它”。RealE2E 的输入输出契约继续沿用：

- 输入：`tools/Webnovel-RealE2E.psm1`
- 结果分类：`environment_blocked` / `mainline_failure` / `page_regression` / `readonly_audit_failure` / `pass`
- 关键产物目录：`real-e2e/`

## 相关入口

- RealE2E 说明：[dashboard-real-e2e.md](dashboard-real-e2e.md)
- 协调器脚本：`tools/Tests/Run-Webnovel-MultiAgentTest.ps1`
- 核心模块：`tools/Webnovel-MultiAgentTest.psm1`

## Dashboard 集成

Dashboard（仪表盘）工作台现在提供 `验证页`，把仓库级 multi-agent test（多子代理测试）接成了一个 workspace-level（工作区级）控制台。

固定行为：

- 启动按钮只会调用正式脚本 `tools\Tests\Run-Webnovel-MultiAgentTest.ps1`。
- Dashboard 内维护单工作区 `active_execution`（活动运行）注册表；同一时刻只允许一个 `starting` / `running` run。
- Dashboard 重启后会先尝试从 `_runtime/active-execution.json` 恢复当前运行，再结合 PID（进程号）存活检查和 `result.json` / `progress.json` 判断为 `running`、`completed`、`incomplete` 或 `failed_to_launch`。
- 页面默认读取最近 10 次 runs（运行记录），优先选中 active run；没有活动运行时选中最新一条历史记录。
- 有活动运行时，高频轮询 `progress`，低频刷新 `overview`，页面会展示 `phase / current_lane / current_step / completed_steps / total_steps / updated_at`。
- 页面会展示 `classification`（分类）、`next_action`（动作码）、`failure_summary`（失败摘要）、`minimal_repro`（最小复现）、`failure_fingerprint`（失败指纹）、`RealE2E` 状态，以及 `report.md`、console stdout/stderr、step 级 stdout/stderr/combined log。
- 详情页会优先聚焦首个失败 step，并默认读取它的 `combined log`（合并日志）。
- 所有日志读取都必须从当前 run 的 step 元数据或固定 console 文件反查，不能把 Dashboard 当作任意文件浏览器。
- `tail_lines` 读取是按需截尾，不会把整份大日志直接回传给前端。
- 页面支持停止当前 active run（活动运行）、重跑历史 run，并显示 `cancelled` / `rerun_after_cancel` 的分诊结果。

后端接口固定挂在：

- `GET /api/workbench/verification/overview`
- `GET /api/workbench/verification/history`
- `POST /api/workbench/verification/run`
- `POST /api/workbench/verification/run/stop`
- `GET /api/workbench/verification/runs/{run_id}`
- `GET /api/workbench/verification/runs/{run_id}/progress`
- `POST /api/workbench/verification/runs/{run_id}/rerun`
- `GET /api/workbench/verification/runs/{run_id}/report`
- `GET /api/workbench/verification/runs/{run_id}/steps/{step_id}/logs/{stream}?tail_lines=200`
- `GET /api/workbench/verification/runs/{run_id}/console/{stream}?tail_lines=200`

其中 `history`（历史）接口支持按 `classification`、`status`、`next_action` 过滤，并按 `failure_fingerprint` 聚合同类失败，便于持续分诊。
