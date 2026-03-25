# Project1

这是一个面向长篇网文创作的 AI 辅助工作台仓库，提供项目启动器、Web 仪表盘（Dashboard）、任务编排、质量审查、状态管理与写作流程支持。

当前仓库由两层组成：

- 仓库根目录：提供 Windows 启动入口、打包脚本与外层工作区封装。
- `webnovel-writer/`：项目核心实现，包含 CLI（命令行）、Dashboard（仪表盘）、写作工作流、数据层与相关文档。

## 项目能力

- Web 仪表盘：用于打开项目、查看任务、管理写作流程与质量面板。
- 写作任务编排：覆盖 `init`、`plan`、`write`、`review`、`repair`、`query`、`resume` 等主流程。
- 多维质量审查：包含一致性、连续性、人物不跑偏、节奏与读者追更拉力等检查环节。
- 项目状态管理：围绕 `.webnovel` 目录维护运行状态、规划信息、修稿备份与报告。
- Windows 友好启动：提供批处理与 PowerShell 脚本，便于本地直接启动工作台。

## 快速开始

Windows 环境下，默认可直接运行：

```text
tools\Start-Webnovel-Writer.bat
```

如需直接启动 PowerShell 脚本，可使用：

```powershell
.\tools\Launch-Webnovel-Dashboard.ps1
```

## 仓库结构

```text
Project1/
├─ README.md
├─ README-启动说明.txt
├─ tools/
└─ webnovel-writer/
   ├─ README.md
   ├─ docs/
   └─ webnovel-writer/
```

## 文档入口

- 项目核心说明：[webnovel-writer/README.md](./webnovel-writer/README.md)
- 文档索引：[webnovel-writer/docs/README.md](./webnovel-writer/docs/README.md)
- 架构说明：[webnovel-writer/docs/architecture.md](./webnovel-writer/docs/architecture.md)
- 命令说明：[webnovel-writer/docs/commands.md](./webnovel-writer/docs/commands.md)
- 运维说明：[webnovel-writer/docs/operations.md](./webnovel-writer/docs/operations.md)

## 适用场景

这个仓库适合用于：

- 长篇网文项目的结构化写作与续写
- 基于任务流的章节生产与修稿
- 结合本地项目状态进行的写作辅助与审查
- 通过 Dashboard 统一查看项目、任务与质量信息
