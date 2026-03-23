# Webnovel Writer

`Webnovel Writer` 是一个面向长篇网文项目的创作工作台，包含任务编排、项目管理、Web 工作台、RAG 检索和项目内控制页面。

详细文档见：
- [`docs/README.md`](docs/README.md)

## 默认启动方式

Windows 下直接双击：

```text
tools\Start-Webnovel-Writer.bat
```

当前默认入口已经切换为“先进入 Web 工作台，再打开或创建项目”：

1. 双击后直接启动 Dashboard 工作台，不再先弹旧菜单或目录选择框。
2. 启动器会检查 `8765` 端口上的现有实例是否属于当前仓库。
3. 不传 `-ProjectRoot` 时使用 `GET /api/workbench/hub` 做工作台健康探测；传入已初始化项目目录时使用 `GET /api/project/director-hub?project_root=...` 做项目健康探测。
4. 只有当现有实例属于当前仓库且当前模式的健康探针返回有效 JSON 时，才会直接复用。
5. 如果发现旧实例仍占端口，但当前模式对应探针返回 HTML 或无效 JSON，会自动停止旧实例并重启最新后端。
6. 只有在健康检查通过后才会打开浏览器。

兼容入口仍然保留：

```powershell
tools\Start-Webnovel-Writer.bat menu
tools\Start-Webnovel-Writer.bat dashboard-lan
tools\Start-Webnovel-Writer.bat login
tools\Start-Webnovel-Writer.bat shell
```

如果直接运行脚本：

```powershell
.\tools\Launch-Webnovel-Dashboard.ps1
```

不传 `-ProjectRoot` 时会进入全局工作台；只有显式传入已初始化项目目录时，才会直接进入单项目视图。

## 工作台结构

工作台采用“左侧项目轨道 + 右侧管理面板”的结构：

- 左侧项目轨道：当前项目、固定项目、最近项目
- 右侧项目主页：当前项目详情、打开已有项目、新建项目、失效记录
- 工具页：登录创作命令行、打开当前项目终端、开启局域网共享、打开快速说明

如果没有活动项目：

- 工作台接口可以正常工作
- 项目型接口会返回 `PROJECT_NOT_SELECTED`
- 应用不会在启动阶段直接崩掉

## 项目页与任务中心

项目页内部继续使用原有路由：

- `control`
- `tasks`
- `data`
- `files`
- `quality`
- `supervisor`
- `supervisor-audit`

当前项目页的核心约定：

- `项目总览`：项目信息、创作指挥台、规划资料、API 设置
- `任务中心`：动作优先，待确认操作尽量在首屏展示
- `查看任务`：只负责进入任务详情
- `执行下一步`：只负责触发推荐动作
- `创作指挥台`：如果接口失败，只在面板内局部降级，不再拖垮整页

## 写作主链

当前 `write` 主链已经切到“先看章节简报，再写正文”的双阶段流程：

- 阶段 A：`story-director -> chapter-director -> chapter-brief-approval`
- 阶段 B：`context -> draft -> consistency-review -> continuity-review -> ooc-review -> review-summary -> polish -> approval-gate -> data-sync`

默认行为：

- 每章先停在 `awaiting_chapter_brief_approval`
- 先批准章节简报，再进入正文阶段
- 只有显式传入 `require_manual_approval = true` 时，正文才会停在回写确认
- `data-sync` 会把长期状态写回 `.webnovel`

## 修稿主链

当前支持单章 `repair` 任务：

- 入口：`POST /api/tasks/repair`
- 流程：`repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`
- 默认自动回写
- 显式传入 `require_manual_approval = true` 时，会停在 `approval-gate`

成功修稿后会生成：

- `.webnovel/repair-backups/`
- `.webnovel/repair-reports/`

## 前端构建

`dashboard/frontend/dist/` 是运行时直接服务的静态目录。修改 `dashboard/frontend/src/` 后，需要在同一次变更中重新构建：

```powershell
Set-Location .\webnovel-writer\dashboard\frontend
npm run build
```

## 文档导航

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/commands.md`](docs/commands.md)
- [`docs/rag-and-config.md`](docs/rag-and-config.md)
- [`docs/genres.md`](docs/genres.md)
- [`docs/operations.md`](docs/operations.md)
- [`docs/README.md`](docs/README.md)
