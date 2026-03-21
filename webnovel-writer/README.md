# Webnovel Writer

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

`Webnovel Writer` 是面向长篇网文项目的写作工作台，包含 CLI、任务编排、Web Dashboard、RAG 检索和项目管理能力。

详细文档见 [`docs/README.md`](docs/README.md)。

## 默认启动方式

Windows 下直接双击：

```text
Start-Webnovel-Writer.bat
```

默认行为已经改成“先进入 Web 工作台，再选/建项目”：

1. 双击后直接启动 Dashboard，不再弹启动前菜单。
2. 不再在启动前要求先选目录或先初始化项目。
3. 在 Web 工作台中通过左侧项目轨道快速切换当前 / 固定 / 最近项目，通过右侧面板执行打开已有项目、新建项目、清理失效记录。
4. 在工作台工具页执行登录 Codex CLI、打开终端、打开说明、开启局域网访问。

兼容入口仍然保留：

```powershell
tools\Start-Webnovel-Writer.bat menu
tools\Start-Webnovel-Writer.bat dashboard-lan
tools\Start-Webnovel-Writer.bat login
tools\Start-Webnovel-Writer.bat shell
```

如果直接运行脚本：

```powershell
.\Launch-Webnovel-Dashboard.ps1
```

不传 `-ProjectRoot` 时会启动全局工作台；只有显式传入一个已初始化项目目录时，才会直接进入单项目视图。

## 工作台能力

工作台首页提供：

- 左侧项目轨道：当前项目、固定项目、最近项目
- 打开已有项目
- 新建项目
- 清理失效记录
- 默认落地偏好：`先到项目主页` / `自动进入上次项目`
- 右侧当前项目详情与管理区
- 工具页入口

工具页提供直接执行按钮：

- 登录 Codex CLI
- 打开当前项目终端
- 打开快速说明
- 开启局域网分享

## 快速开始

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

如需开发依赖：

```powershell
python -m pip install -e ".[dev,dashboard]"
```

### 2. 首次创建项目

有两种方式：

1. 在 Dashboard 工作台首页点击“新建项目”，先选目录，再填写标题和题材。
   新建完成后，Planning Profile 默认保持空白待填，不会再自动灌入整套示例人物与卷设定。
2. 或先在命令行运行：

```powershell
webnovel init
```

初始化后项目目录会包含：

```text
.webnovel/
正文/
大纲/
设定集/
```

### 3. 配置写作模型和 RAG

推荐在 Dashboard 的 `总览 -> API 接入设置` 中填写：

- 写作模型：`Provider`、`Base URL`、`模型名`、`API Key`
- RAG：`Base URL`、`Embedding 模型`、`Rerank 模型`、`API Key`

保存后会写入项目根目录 `.env`。

### 4. 开始使用

```powershell
webnovel plan 1
webnovel write 1
webnovel review 1-5
```

## Dashboard 说明

项目页仍然以 `project_root` 作为当前活动项目的权威来源。没有活动项目时：

- 工作台接口可正常工作
- 项目型接口会返回 `PROJECT_NOT_SELECTED`
- 不会在应用启动阶段直接崩掉

项目页继续复用现有模块：

- `control`
- `tasks`
- `data`
- `files`
- `quality`
- `supervisor`
- `supervisor-audit`

项目内首页和任务页的默认交互现已统一为：

- `总览`：项目内首页，负责项目信息、规划资料、主线任务入口和 API 设置
- `任务中心`：优先展示用户动作，首屏固定 `批准回写 / 拒绝回写 / 按当前步骤重跑 / 创建局部修稿任务`
- `查看任务` 只负责导航到任务详情
- `执行下一步` 只负责触发当前推荐动作
- `问题汇总`、`待人工确认`、`局部修稿` 为前端统一术语，不再直出内部英文步骤名
- 活跃任务存在时会自动启用高频轮询；SSE 只作为刷新提示，不再是唯一刷新来源

## Repair Mainline

当前支持单章 `repair` 任务：

- 启动入口：`POST /api/tasks/repair`
- 工作流：`repair-plan -> repair-draft -> consistency-review -> continuity-review -> review-summary -> approval-gate -> repair-writeback`
- 默认自动回写
- 如果显式传入 `require_manual_approval = true`，任务会停在 `approval-gate`
- `repair-draft / consistency-review / continuity-review` 已接入一次性 `INVALID_STEP_OUTPUT` 自动重试

成功修稿会生成：

- `.webnovel/repair-backups/`
- `.webnovel/repair-reports/`

## 前端产物

`dashboard/frontend/dist/` 是 Dashboard 运行时直接服务的静态目录。修改 `dashboard/frontend/src/` 后，需要在同一次变更里执行并提交：

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
