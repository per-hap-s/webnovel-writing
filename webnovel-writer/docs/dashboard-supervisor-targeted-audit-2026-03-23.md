# 督办 smoke 夹具与定向真实巡检记录（2026-03-23）

本记录保留首次 targeted real audit（定向真实巡检）的失败事实，用于说明本轮中文优先文案问题是如何被真实页面稳定复现的。修复后复验通过记录见 `dashboard-supervisor-language-fix-verification-2026-03-23.md`。

## 环境

- 复验日期：2026-03-23
- 工作目录：`D:\CodexProjects\Project1`
- Dashboard 地址：`http://127.0.0.1:8765`
- 夹具项目：`D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260323\supervisor-smoke-191940`
- 产物目录：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323`

## 夹具摘要

- 夹具入口：`python D:\CodexProjects\Project1\webnovel-writer\webnovel-writer\scripts\supervisor_smoke_fixture.py`
- 生成结果：
  - `recommendation_count = 2`
  - `checklist_count = 1`
  - `audit_log_count = 6`
  - `audit_health.exists = true`
  - `audit_health.issue_count = 2`
  - `repair_preview.manual_review_count = 2`
  - `repair_report_count = 1`
- 夹具结果文件：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\fixture-result.json`

## 入口

- 启动入口：`& 'D:\CodexProjects\Project1\tools\Start-Webnovel-Writer.ps1' -Action dashboard -ProjectRoot 'D:\CodexProjects\Project1\webnovel-writer\.tmp-playwright-20260323\supervisor-smoke-191940' -NoBrowser`
- 预检文件：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\precheck.json`
- 真实页面：
  - `http://127.0.0.1:8765/?project_root=D%3A%5CCodexProjects%5CProject1%5Cwebnovel-writer%5C.tmp-playwright-20260323%5Csupervisor-smoke-191940&page=supervisor`
  - `http://127.0.0.1:8765/?project_root=D%3A%5CCodexProjects%5CProject1%5Cwebnovel-writer%5C.tmp-playwright-20260323%5Csupervisor-smoke-191940&page=supervisor-audit`

## 预检结果

- 6 个 supervisor API（接口）全部命中阈值：
  - `recommendations = 2`
  - `checklists = 1`
  - `audit_log = 6`
  - `audit_health.exists = true`，`issue_count = 2`
  - `audit_repair_preview.exists = true`，`manual_review_count = 2`
  - `audit_repair_reports = 1`
- 结论：夹具通过，本轮问题进入真实 UI（界面）判断阶段。

## 页面结果

### `supervisor`

- 活动建议区与已保存清单区均为非空。
- 页级 `督办台数据刷新失败` 未出现。
- 真实缺陷已复现：
  - 页面仍直接暴露 `approval-gate`
  - 页面仍直接暴露 `hard blocking issue`

### `supervisor-audit`

- 时间线、审计体检、修复预演、修复归档、清单归档均为非空。
- 页级 `督办审计数据刷新失败` 未出现。
- 真实缺陷已复现：
  - 页面仍直接暴露 `Detected audit schema`
  - 页面仍直接暴露 `through v2`

## 快照索引

- 转录：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\playwright-transcript.txt`
- 快照索引：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\snapshot-index.txt`
- 截图索引：`D:\CodexProjects\Project1\output\verification\supervisor-targeted-audit-20260323\screenshot-index.txt`
- 实际快照：
  - `D:\CodexProjects\Project1\.playwright-cli\page-2026-03-23T11-19-54-184Z.yml`
  - `D:\CodexProjects\Project1\.playwright-cli\page-2026-03-23T11-20-02-087Z.yml`
- 实际截图：
  - `D:\CodexProjects\Project1\.playwright-cli\page-2026-03-23T11-19-56-813Z.png`
  - `D:\CodexProjects\Project1\.playwright-cli\page-2026-03-23T11-20-04-352Z.png`

## 是否放行

- 结论：不放行
- 判定：`ui_defect_reproduced`
- 说明：预检与数据阈值均已命中，页面也不再是“全空”；当前阻断点是中文优先文案未收口，已从真实页面稳定复现为 UI 缺陷。

## 遗留问题

- 后续修复按页面拆包，不与启动器、质量页、任务中心混流：
  - `supervisor`：清理 `approval-gate`、`hard blocking issue` 等内部英文词
  - `supervisor-audit`：清理 `Detected audit schema`、`through v2` 等 future schema（未来版本结构）英文提示
- 修复后通过记录：`dashboard-supervisor-language-fix-verification-2026-03-23.md`
