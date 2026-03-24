# Dashboard Real E2E（真实全链路实测）

## 目标

这套 real e2e（真实全链路实测）用于版本级验收当前小说写作项目是否已经达到“可持续实用”状态。

默认覆盖链路：

- `bootstrap`
- `planning-profile`
- `plan`
- `write 1-3`
- `review 1-3`
- `repair`（仅在 review 给出可修复候选时触发）
- `control / tasks / quality`
- `readonly audit`

默认不新增任何 public API（公开接口）或一次性临时协议，只复用仓库内现有接口与正式脚本。

## 正式入口

在 PowerShell（PowerShell）里运行：

```powershell
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1'
```

常用参数：

```powershell
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -PreferredPort 8765
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -OutputRoot 'D:\CodexProjects\Project1\output\verification\real-e2e\manual-run'
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -RunId 'manual01'
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -ProjectRoot 'D:\path\to\existing-project'
& '.\tools\Tests\Run-Webnovel-RealE2E.ps1' -Title 'Night Rain Rewind' -Genre 'Urban Supernatural'
```

说明：

- 不传 `-ProjectRoot` 时，会自动创建 `webnovel-writer\.tmp-real-e2e-<YYYYMMDD>-<runid>` 临时项目。
- 默认会顺序跑 3 章，不扩到 5 章以上。
- `repair` 不是强制阶段；只有 review 命中可自动修复候选时才会触发。
- 最终 JSON（结构化结果）会直接打印到终端，同时写入产物目录。

## 固定流程

1. 启动隔离端口上的 Dashboard（工作台）并记录环境基线。
2. 调用 `POST /api/project/bootstrap` 创建真实临时项目。
3. 读取并保存一次 `Planning Profile`，确认冷启动计划输入链可直接使用。
4. 执行 `plan volume=1`。
5. 顺序执行 `write chapter=1..3`，在 `awaiting_chapter_brief_approval` 时自动批准章节简报。
6. 执行 `review chapter_range=1-3`，要求输出结构化 `blocking / can_proceed / severity_counts`。
7. 若 review 暴露白名单修稿候选，则执行 1 次 `repair` 并验证备份/报告目录。
8. 用 Playwright（浏览器自动化）检查 `control / tasks / quality` 页面。
9. 在同一项目上执行既有 `readonly audit`。
10. 汇总结果并写出最终 `acceptance-report.md`。

## 产物目录

默认产物会落在：

```text
output/verification/real-e2e/YYYYMMDD-runid/
```

固定产物：

- `environment.json`
- `bootstrap-response.json`
- `planning-profile-before.json`
- `planning-profile-after.json`
- `task-summary-plan.json`
- `task-summary-write-ch1.json`
- `task-summary-write-ch2.json`
- `task-summary-write-ch3.json`
- `task-summary-review-1-3.json`
- `task-summary-repair.json`
- `project-state-final.json`
- `readonly-audit-result.json`
- `acceptance-report.md`

附加产物：

- `dashboard-pages.json`
- `dashboard-playwright-transcript.txt`
- `dashboard-snapshot-index.txt`
- `dashboard-screenshot-index.txt`
- `readonly-audit/`（下挂 readonly audit 的标准产物）

## 通过标准

只有在以下条件同时满足时，`classification` 才能为 `pass`：

- 冷启动后无需手工改 `总纲.md` 即可完成 `plan`
- `write 1-3` 全部闭环
- `review 1-3` 成功输出结构化结论
- 若触发 `repair`，则 `repair` 能写出备份与报告
- `control / tasks / quality` 页面不出现明显回退
- `readonly audit` 最终 `classification = pass`
- 项目目录中存在 3 章正文、3 章摘要、卷规划与状态同步结果

## 失败归因

最终结果使用以下 `classification`：

- `environment_blocked`
  环境阻断，例如模型配置、Key（密钥）、Node/Playwright 缺失。
- `mainline_failure`
  `plan / write / review / repair` 任一主链步骤未闭环，或最终落盘结果不完整。
- `page_regression`
  `control / tasks / quality` 页面出现回退，但主链和 readonly audit 已可继续判断。
- `readonly_audit_failure`
  主链通过，但 readonly audit 未达到 `pass`。
- `pass`
  全部阶段通过。

## 相关文件

- 脚本入口：`tools/Tests/Run-Webnovel-RealE2E.ps1`
- 核心模块：`tools/Webnovel-RealE2E.psm1`
- Dashboard 启动模块：`tools/Webnovel-DashboardLauncher.psm1`
- 只读巡检：`tools/Tests/Run-Webnovel-ReadonlyAudit.ps1`
- 只读巡检说明：`dashboard-readonly-audit.md`
