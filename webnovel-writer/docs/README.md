# 文档中心

本目录承载 `README.md` 之外的详细说明，按模块拆分：

- [架构与模块](#架构与模块)
- [命令详解](#命令详解)
- [RAG 与配置](#rag-与配置)
- [题材模板](#题材模板)
- [运维与恢复](#运维与恢复)
- [真实回归](#真实回归)

## 架构与模块

- `architecture.md`：系统架构、核心理念、双 Agent、六维审查

## 命令详解

- `commands.md`：`webnovel init / plan / write / review / resume / dashboard` 命令详细说明

## RAG 与配置

- `rag-and-config.md`：RAG 检索、项目 `.env`、以及面板内 API 接入设置说明

## 题材模板

- `genres.md`：题材模板与复合题材规则

## 运维与恢复

- `operations.md`：项目结构与故障恢复/运维手册

## 真实回归

- `dashboard-launcher-ui-real-verification-2026-03-23.md`：启动器复用路径、隔离端口冷重启旁证、质量页低数据 smoke，以及项目总览/数据页中文收口复验
- `dashboard-supervisor-targeted-audit-2026-03-23.md`：督办 smoke 夹具首次定向真实巡检；保留 `ui_defect_reproduced` 历史事实与原始失败归档
- `dashboard-supervisor-language-fix-verification-2026-03-23.md`：督办页面英文泄漏修复后的复验记录，确认 `supervisor` / `supervisor-audit` 两页重新达到 `pass`
- `dashboard-readonly-audit-2026-03-23.md`：启动入口、核心页面与窄屏的只读巡检归档
- `dashboard-api-real-test-3ch-phase3-2026-03-21.md`：第三阶段后 `bootstrap -> plan -> write 1-3 -> review 1-3` 真实回归结果

建议阅读顺序：

1. 先看 `../README.md`（安装、启动顺序、面板 API 设置）
2. 再看 `architecture.md`（理解系统设计）
3. 最后按需查阅命令和运维文档
