# Dashboard Readonly Audit（只读巡检）

## 目标

这套 readonly audit（只读巡检）用于复验 Dashboard（工作台）里的只读页面，不引入任何写回操作。

当前正式覆盖：

- `supervisor`
- `supervisor-audit`

默认流程会先生成 smoke fixture（冒烟夹具），再启动隔离端口上的 Dashboard，最后通过 Playwright（浏览器自动化）抓取真实页面快照、截图和文本转录。

## 正式入口

在 PowerShell（PowerShell）里运行：

```powershell
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1'
```

常用参数：

```powershell
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -PreferredPort 8765
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -OutputRoot 'D:\CodexProjects\Project1\output\verification\readonly-audit\manual-run'
& '.\tools\Tests\Run-Webnovel-ReadonlyAudit.ps1' -ProjectRoot 'D:\path\to\existing-supervisor-smoke-project'
```

说明：

- 不传 `-ProjectRoot` 时，会先调用 `supervisor_smoke_fixture.py` 生成新的夹具项目。
- 优先尝试复用 `8765`；若已被占用，会自动回退到 `8876..8895` 的隔离端口。
- 输出 JSON（结构化结果）会直接打印到终端，同时写入产物目录。

## 产物目录

默认产物会落在：

```text
output/verification/readonly-audit/run-YYYYMMDD-HHmmss/
```

固定产物：

- `fixture-result.json`
- `precheck.json`
- `playwright-transcript.txt`
- `snapshot-index.txt`
- `screenshot-index.txt`
- `result.json`

其中：

- `fixture-result.json` 记录夹具生成结果。
- `precheck.json` 记录 6 个 supervisor API（接口）预检是否全部命中阈值。
- `playwright-transcript.txt` 记录 Playwright 操作转录。
- `snapshot-index.txt` / `screenshot-index.txt` 记录本次真实页面快照和截图路径。
- `result.json` 是最终归因结果，包含 `classification`、`dashboard_port`、`base_url`、页面级检查结果等信息。

## 成功标准

预检必须全部通过，至少包括：

- `recommendations >= 2`
- `checklists >= 1`
- `audit_log >= 1`
- `audit_health.exists = true`
- `audit_health.issue_count >= 1`
- `audit_repair_preview.exists = true`
- `audit_repair_preview.manual_review_count >= 1`
- `audit_repair_reports >= 1`

页面级固定验收点：

- `supervisor` 不应落回“当前没有需要优先处理的建议”“暂时还没有已保存的清单”等空态。
- `supervisor-audit` 不应落回“当前筛选条件下暂无审计事件”“当前没有可预演的修复动作”等空态。
- 页面文案保持中文优先，不暴露 `manual-only`、`approval-gate`、`hard blocking issue`、`Detected audit schema`、`through v2` 这类内部英文词。

## 失败归因

`result.json` 里的 `classification` 当前使用以下口径：

- `fixture_failure`
  预检未命中阈值，先修夹具或接口，不进入 UI（界面）判断。
- `ui_defect_reproduced`
  预检全部命中，但真实页面仍暴露空态、英文内部词或页级错误。
- `pass`
  预检和真实页面检查全部通过。
- `verification_complete_docs_pending`
  只跑了接口预检，跳过了浏览器验收；仅用于特殊场景，不算正式放行。

## 相关文件

- 脚本入口：`tools/Tests/Run-Webnovel-ReadonlyAudit.ps1`
- 核心模块：`tools/Webnovel-ReadonlyAudit.psm1`
- 夹具脚本：`webnovel-writer/scripts/supervisor_smoke_fixture.py`
- Launcher（启动器）：`tools/Start-Webnovel-Writer.ps1`
- 历史实录：`dashboard-supervisor-targeted-audit-2026-03-23.md`
- 修复后复验：`dashboard-supervisor-language-fix-verification-2026-03-23.md`
