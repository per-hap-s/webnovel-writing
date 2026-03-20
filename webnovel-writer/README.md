# Webnovel Writer

[![License](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-purple.svg)](https://claude.ai/claude-code)

## 项目简介

`Webnovel Writer` 是一个面向长篇网文项目的写作工作台，包含：

- 命令行工作流：`webnovel init / plan / write / review / resume / dashboard`
- Windows 启动器：双击即可打开面板、登录 Codex CLI、查看快速说明
- Web Dashboard：项目概览、任务监控、数据查询、文件浏览、质量面板
- 面板内 API 配置：可直接修改写作模型和 RAG 配置，并写回项目根目录 `.env`

详细文档见 [`docs/README.md`](docs/README.md)。

## 推荐启动方式

### Windows 用户

推荐直接双击以下文件：

```text
Start-Webnovel-Writer.bat
```

启动器菜单包含：

1. 启动本机 Dashboard
2. 启动局域网 Dashboard
3. 登录 Codex CLI
4. 打开项目终端
5. 打开中文快速说明

如果你选择的目录还没有初始化为小说项目，启动器会先询问小说标题和题材，并自动创建 `.webnovel/state.json`。

### 命令行用户

也可以直接运行：

```powershell
webnovel dashboard
```

或使用 PowerShell 脚本：

```powershell
.\Launch-Webnovel-Dashboard.ps1
```

以下命令示例默认都以 PowerShell 为准。

## 快速上手

### 1. 安装插件

```powershell
claude plugin marketplace add lingfengQAQ/webnovel-writer --scope user
claude plugin install webnovel-writer@webnovel-writer-marketplace --scope user
```

如果只想在当前项目生效，把 `--scope user` 改成 `--scope project`。

### 2. 安装 Python 依赖

```powershell
python -m pip install -r https://raw.githubusercontent.com/lingfengQAQ/webnovel-writer/HEAD/requirements.txt
```

这会同时安装写作链路和 Dashboard 依赖。

### 3. 初始化项目

在目标工作区执行：

```powershell
webnovel init
```

初始化完成后，项目根目录下会生成：

```text
.webnovel/
正文/
大纲/
设定集/
```

初始化完成后，系统会同时写入一份可直接编辑的 `.webnovel/planning-profile.json`，并生成更完整的 `大纲/总纲.md` 最小骨架。默认推荐流程是：

1. 打开 Dashboard 的 `Planning Profile`
2. 确认并保存规划信息
3. 再运行 `webnovel plan 1`

### 4. 配置写作模型和 RAG

推荐优先使用 Dashboard 的 `总览 -> API 接入设置`：

- 写作模型 API：`Provider`、`Base URL`、`模型名称`、`API Key`
- RAG API：`Base URL`、`Embedding 模型`、`Rerank 模型`、`API Key`

保存后会：

1. 写入项目根目录 `.env`
2. 立即刷新面板状态
3. 后续任务直接使用新配置

如果 API Key 输入框留空，则会保留当前已保存的 Key。

也可以手动编辑项目根目录 `.env`。当前面板写入的核心变量如下：

```powershell
$env:WEBNOVEL_LLM_PROVIDER = "openai-compatible"
$env:WEBNOVEL_LLM_BASE_URL = "https://api.openai.com/v1"
$env:WEBNOVEL_LLM_MODEL = "gpt-4.1-mini"
$env:WEBNOVEL_LLM_API_KEY = "your_llm_api_key"

$env:WEBNOVEL_RAG_BASE_URL = "https://api.siliconflow.cn/v1"
$env:WEBNOVEL_RAG_EMBED_MODEL = "BAAI/bge-m3"
$env:WEBNOVEL_RAG_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
$env:WEBNOVEL_RAG_API_KEY = "your_rag_api_key"
```

补充说明：

- 如果你准备用 `Codex CLI` 作为写作执行器，可以先在启动器里选择“登录 Codex CLI”。
- 当未配置写作模型 API、但本机可用 `Codex CLI` 时，Dashboard 会优先回退到 CLI 模式。
- 面板仍兼容读取 `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`，但新配置建议统一使用 `WEBNOVEL_LLM_*`。

### 5. 开始使用

```powershell
webnovel plan 1
webnovel write 1
webnovel review 1-5
```

如果首轮 `plan` 仍因输入不足被阻断，任务会返回 `PLAN_INPUT_BLOCKED`，并在错误详情里附带结构化 `blocking_items`。这表示需要补齐规划输入，而不是模型超时或系统异常；此时不会生成或覆盖空壳 `volume-01-plan.md`。

## Dashboard 当前能力

当前 Dashboard 不再是“纯只读页面”。它包含两类能力：

- 可视化查看：项目状态、实体、关系、章节、文件、质量数据
- 控制与配置：创建任务、重试任务、审批回写、确认失效事实、保存 API 配置

与启动说明直接相关的几个入口如下：

- `总览 -> 项目创建`
- `总览 / 控制页 -> Planning Profile`
- `总览 -> 任务入口`
- `总览 -> API 接入设置`
- `任务 -> 任务监控 / 批准回写 / 拒绝回写`

其中“文件”页面仍然是受限只读，只允许读取项目根目录下的 `正文`、`大纲`、`设定集`。

## 面板 API 修改说明

如果你不是通过界面，而是要从脚本或外部面板接入，当前后端提供：

- `POST /api/project/bootstrap`
- `POST /api/settings/llm`
- `POST /api/settings/rag`

对应保存行为：

- `POST /api/project/bootstrap` 会初始化项目目录、写入最小 `planning-profile` 与总纲骨架，并返回下一步建议到 `Planning Profile`
- `POST /api/settings/llm` 会更新 `WEBNOVEL_LLM_PROVIDER`、`WEBNOVEL_LLM_BASE_URL`、`WEBNOVEL_LLM_MODEL`、`WEBNOVEL_LLM_API_KEY`
- `POST /api/settings/rag` 会更新 `WEBNOVEL_RAG_BASE_URL`、`WEBNOVEL_RAG_EMBED_MODEL`、`WEBNOVEL_RAG_RERANK_MODEL`、`WEBNOVEL_RAG_API_KEY`

接口保存位置都是项目根目录 `.env`，不会修改系统级环境变量文件。

`plan` 相关任务如果因为规划资料缺失失败，会统一返回错误码 `PLAN_INPUT_BLOCKED`，并在 `details.blocking_items` 中列出缺失字段。

## Frontend 门禁与产物

- `dashboard/frontend/dist/` 是 Dashboard 运行时直接服务的静态产物目录，当前保持入库。
- 如果修改了 `dashboard/frontend/src/`，同一次变更中需要运行 `npm run build` 并提交对应的 `dist/` 更新。
- 前端默认自检门禁包括 `npm run lint`、`npm run typecheck`、`npm run test:state`、`npm run test:ui` 和 `npm run build`。

## 文档导航

- 架构与模块：[`docs/architecture.md`](docs/architecture.md)
- 命令详解：[`docs/commands.md`](docs/commands.md)
- RAG 与配置：[`docs/rag-and-config.md`](docs/rag-and-config.md)
- 题材模板：[`docs/genres.md`](docs/genres.md)
- 运维与恢复：[`docs/operations.md`](docs/operations.md)
- 文档索引：[`docs/README.md`](docs/README.md)

## 更新简介

| 版本 | 说明 |
|------|------|
| **v5.5.0 (当前)** | 提供 Dashboard、任务编排、API 接入设置与实时刷新能力 |
| **v5.4.4** | 引入官方 Plugin Marketplace 安装流程 |
| **v5.4.3** | 增强 RAG 检索与回退策略 |
| **v5.3** | 引入追读力与质量跟踪体系 |

## 开源协议

本项目使用 `GPL v3` 协议，详见 [`LICENSE`](LICENSE)。

## Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=lingfengQAQ/webnovel-writer&type=Date)](https://star-history.com/#lingfengQAQ/webnovel-writer&Date)

## 致谢

本项目使用 **Claude Code + Gemini CLI + Codex** 协同开发。

灵感来源：[Linux.do 帖子](https://linux.do/t/topic/1397944/49)

## 贡献

欢迎提交 Issue 和 PR：

```powershell
git checkout -b feature/your-feature
git commit -m "feat: add your feature"
git push origin feature/your-feature
```
