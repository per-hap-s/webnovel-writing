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

## Dashboard 真实复验操作口径

### 启动器冷重启旁证

当需要验证“坏实例替换 / 冷重启”时，优先使用隔离端口受控场景，不直接强杀正在服务的主实例。

推荐步骤：

1. 选一个未占用端口，例如 `8877`。
2. 启动一个受控监听器，让它的命令行显式包含 `dashboard.server --workspace-root <WORKSPACE_ROOT>`，但对 `GET /api/workbench/hub` 只返回 `text/html`。
3. 先确认预探针结果是：
   - `StatusCode = 200`
   - `ContentType = text/html; charset=utf-8`
4. 运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Launch-Webnovel-Dashboard.ps1 -Port 8877 -NoBrowser
```

5. 成功口径：
   - 决策输出包含 `stale_restart`
   - 日志包含 `Stop result: stopped PID ...`
   - 随后 `/api/workbench/hub` 返回 `application/json`
6. 若清理失败是 `permission_denied` 或当前用户无权结束旧进程，应归类为环境问题，不应直接判为启动器逻辑回归。

### 质量页低数据 smoke 场景

当需要验证质量页低数据态的真实展示时，使用 bootstrap 后不补写运行记录的新项目。

推荐步骤：

1. 通过 `POST /api/project/bootstrap` 创建临时项目，例如放在 `webnovel-writer\.tmp-playwright-YYYYMMDD\low-data-smoke-*`。
2. 保持项目只有 bootstrap 默认数据，不预先写入：
   - 审查指标
   - 清单评分
   - 检索调用
   - 工具统计
3. 打开：

```powershell
http://127.0.0.1:8765/?project_root=<url-encoded-project-root>&page=quality
```

4. 成功口径：
   - 出现 `当前质量页仍处于低数据态`
   - 出现 `还缺少 4 类关键质量记录，当前趋势判断会偏弱。`
   - 四张摘要卡都出现对应中文空态说明

### 督办 smoke 夹具 + 定向真实巡检

当需要验证 `supervisor` 与 `supervisor-audit` 两页不再是“全空盲区”时，先生成独立的督办 smoke fixture（冒烟夹具），再做只覆盖这两页的 targeted real audit（定向真实巡检）。

推荐步骤：

1. 先生成夹具项目：

```powershell
python (Join-Path $env:SCRIPTS_DIR "supervisor_smoke_fixture.py")
```

默认输出到 `D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-YYYYMMDD\supervisor-smoke-<HHmmss>`；如需复跑固定目录，可显式传入：

```powershell
python (Join-Path $env:SCRIPTS_DIR "supervisor_smoke_fixture.py") --project-root 'D:\path\to\supervisor-smoke-project'
```

2. 再用项目模式启动 Dashboard（工作台）：

```powershell
& 'D:\CodexProjects\Project1\tools\Start-Webnovel-Writer.ps1' -Action dashboard -ProjectRoot '<fixture-project>' -NoBrowser
```

3. 启动后先做 6 个 HTTP（接口）预检，全部命中才进入真实页面：
   - `GET /api/supervisor/recommendations?include_dismissed=true&project_root=...`：至少 2 条
   - `GET /api/supervisor/checklists?project_root=...`：至少 1 条
   - `GET /api/supervisor/audit-log?project_root=...`：非空
   - `GET /api/supervisor/audit-health?project_root=...`：`exists=true` 且 `issue_count>=1`
   - `GET /api/supervisor/audit-repair-preview?project_root=...`：`exists=true` 且 `manual_review_count>=1`
   - `GET /api/supervisor/audit-repair-reports?project_root=...`：至少 1 条
4. 只巡检两个真实页面：
   - `http://127.0.0.1:8765/?project_root=<url-encoded-project-root>&page=supervisor`
   - `http://127.0.0.1:8765/?project_root=<url-encoded-project-root>&page=supervisor-audit`
5. 固定验收点：
   - `supervisor` 页必须出现非空活动建议区与已保存清单区，且没有页级 `督办台数据刷新失败`
   - `supervisor-audit` 页的时间线、审计体检、修复预演、修复归档、清单归档都不能落回空态，且没有页级 `督办审计数据刷新失败`
   - 页面文案保持中文优先，不应暴露 `manual-only`、`approval-gate`、`hard blocking issue`、`Detected audit schema` 这类内部英文词
6. 固定产物目录：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\`
   - `fixture-result.json`
   - `precheck.json`
   - `playwright-transcript.txt`
   - `snapshot-index.txt`
   - `screenshot-index.txt`
   - `result.json`
   - 至少 2 张截图与对应 `.playwright-cli/page-*.yml`
7. 若默认端口 `8765` 已被健康旧实例占用，复验脚本可以改用空闲隔离端口，但必须同时满足：
   - 仍通过 `& 'D:\CodexProjects\Project1\tools\Start-Webnovel-Writer.ps1' -Action dashboard -ProjectRoot '<fixture-project>' -Port <isolated-port> -NoBrowser` 启动
   - 在 `result.json` 中记录实际 `dashboard_port` 与 `base_url`
   - 文档归档明确说明此次复验为何没有复用 `8765`
8. 失败归因固定化：
   - 预检未命中阈值：归类为“夹具失败”，先修夹具，不进入 UI 判断
   - 预检全部命中但页面仍空、仍报页级错误、或暴露内部英文词：归类为“真实页面缺陷已复现”，只输出后续分包
   - 页面通过但产物或文档未落档：归类为“验证完成、收口未完成”，不算闭环

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
