# 项目结构与运维

## 目录层级

运行时建议统一使用这几个路径概念：

1. `WORKSPACE_ROOT`：你的工作区根目录。
2. `WORKSPACE_ROOT/.webnovel/`：工作区级指针与缓存目录。
3. `PROJECT_ROOT`：真实小说项目根目录，由 `webnovel init` 创建。
4. `PLUGIN_ROOT`：插件或仓库代码目录。

### Workspace 目录

```text
workspace-root/
├── .webnovel/
│   ├── current-project
│   └── settings.json
├── 小说A/
├── 小说B/
└── ...
```

### 小说项目目录

```text
project-root/
├── .webnovel/
├── 正文/
├── 大纲/
└── 设定集/
```

## Dashboard 工作台启动语义

当前默认入口已经是“全局壳模式”：

- 启动脚本默认不再要求 `PROJECT_ROOT`。
- 双击 `Start-Webnovel-Writer.bat` 会直接启动 Web 工作台。
- 工作台接口负责项目选择、项目注册、最近项目/固定项目、工具动作。
- 项目页继续使用 `project_root` 查询参数作为当前活动项目的权威来源。
- 无活动项目时，项目型 API 应返回 `PROJECT_NOT_SELECTED`，而不是在应用启动阶段崩溃。

工作区注册需要维护：

- `.webnovel/current-project`
- 工作区注册表中的 `current_project_root`
- `recent_projects[]`
- `pinned_project_roots[]`

## 常用环境变量

```powershell
$env:WORKSPACE_ROOT = if ($env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT } else { (Get-Location).Path }
$env:PLUGIN_ROOT = "D:\path\to\webnovel-writer"
$env:SCRIPTS_DIR = Join-Path $env:PLUGIN_ROOT "scripts"
$env:PROJECT_ROOT = python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:WORKSPACE_ROOT where
```

## 常用运维命令

### 索引检查

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT index stats
```

### 状态报告

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT status -- --focus all
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT status -- --focus urgency
```

### RAG 检查

```powershell
python (Join-Path $env:SCRIPTS_DIR "webnovel.py") --project-root $env:PROJECT_ROOT rag stats
```

### 测试入口

```powershell
pwsh (Join-Path $env:PLUGIN_ROOT "scripts/run_tests.ps1") -Mode smoke
pwsh (Join-Path $env:PLUGIN_ROOT "scripts/run_tests.ps1") -Mode full
```

### 开发依赖前置

在直接运行 `pytest`、打包或前端静态检查之前，先安装开发依赖：

```powershell
python -m pip install -e "$($env:PLUGIN_ROOT)[dev,dashboard]"
Set-Location (Join-Path $env:PLUGIN_ROOT "dashboard/frontend")
npm install
```

说明：

- `pytest-cov` 属于 Python 测试前置依赖；如果未安装，仓库根的 `pytest` 配置会因覆盖率参数缺失而失败。
- `npm run lint`、`npm run typecheck`、`npm run test:*` 都依赖前端本地 `node_modules/`。

## Dashboard Frontend Artifact Maintenance

`dashboard/frontend/dist/` is the runtime static asset directory for the dashboard and remains committed in this project.

Rules:

- If `dashboard/frontend/src/` changes, run `npm run build` and commit the resulting `dist/` update in the same change.
- `dist/index.html` and `dist/assets/` must come from the same build output.
- Remove superseded hashed files from `dist/assets/` when a new build replaces them.

## Runtime State File Discipline

`.webnovel/state.json` is a shared runtime file for dashboard and orchestration flows.

Rules:

- Read and write it through the shared state access layer in `scripts/data_modules/state_file.py`.
- Runtime writes must follow `FileLock` + lock-in reread + incremental mutation + atomic write.
- Do not add new direct `read_text()/write_text()` mutation paths for `.webnovel/state.json`.

## Cold-Start Planning Operations

Bootstrap and first-run planning now follow a fixed minimum-input contract.

Rules:

- `POST /api/project/bootstrap` must seed both `.webnovel/planning-profile.json` and a usable `大纲/总纲.md` skeleton.
- The recommended first action after bootstrap is to open `Planning Profile`, confirm the generated fields, and save once before running `plan`.
- `plan` preflight merges inputs in this order: `.webnovel/planning-profile.json` -> `.webnovel/state.json` `planning.project_info` -> `大纲/总纲.md`.
- If required planning inputs are still missing, `plan` must fail with `PLAN_INPUT_BLOCKED` and include `details.blocking_items`.
- When `PLAN_INPUT_BLOCKED` is returned, do not expect `大纲/volume-01-plan.md` or `planning.volume_plans[1]` to be updated.

## Invalid Step Output Recovery

Dashboard mainline tasks now standardize `INVALID_STEP_OUTPUT` semantics instead of treating all parse failures as the same terminal error.

Rules:

- `INVALID_STEP_OUTPUT` must preserve the original error code and expose structured `details`.
- `details` must include:
  - `parse_stage`
  - `raw_output_present`
  - `missing_required_keys`
  - `recoverability`
  - `suggested_resume_step`
- `recoverability` is constrained to:
  - `auto_retried`: the orchestrator has already scheduled the one allowed automatic retry for this step.
  - `retriable`: the step was not auto-retried, but the failure is still safe to retry manually.
  - `terminal`: the step has exhausted automatic recovery for this failure class.
- Automatic retry is enabled once for:
  - `plan.plan`
  - `repair.repair-draft`
  - `repair.consistency-review`
  - `repair.continuity-review`
  - `write.context`
  - `write.draft`
  - `write.polish`
  - `write.consistency-review`
  - `write.continuity-review`
  - `write.ooc-review`
  - `review.consistency-review`
  - `review.continuity-review`
  - `review.ooc-review`
- `data-sync` remains excluded from automatic retry in this phase; if it fails with `INVALID_STEP_OUTPUT`, it should surface as `retriable` with `suggested_resume_step = data-sync`.

## Repair Task

Dashboard now supports a dedicated chapter-level `repair` task instead of folding automatic rewrite into `review`.

Rules:

- Launch path: `POST /api/tasks/repair`
- Default behavior: direct writeback after task launch, unless the request explicitly sets `require_manual_approval = true`
- Workflow: `repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`
- Automatic writeback is allowed only when:
  - the issue type is in the repair whitelist
  - repair review is not blocking
  - the task has either passed `approval-gate` or does not require manual approval
  - a chapter backup is written before overwrite
- If `require_manual_approval = true`, the task must pause at `approval-gate` with `status = awaiting_writeback_approval` before overwrite.
- If repair review still blocks the chapter, the task must fail with `REPAIR_REVIEW_BLOCKED` and must not overwrite the chapter body.
