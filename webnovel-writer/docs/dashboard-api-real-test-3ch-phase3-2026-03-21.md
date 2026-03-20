# Dashboard API 三章真实回归报告（Phase 3）

## 基本信息
- 测试日期：2026-03-21
- 测试模式：真实 API
- 主链路：Dashboard API
- 测试项目目录：`D:\CodexProjects\Project1\webnovel-writer\.tmp-real-phase3b-20260321`
- 书名：`Night Rain Rewind Phase3`
- 题材：`Urban Supernatural`
- 验收目标：验证第三阶段后的 `bootstrap -> plan -> write 1 -> write 2 -> write 3 -> review 1-3` 是否能在冷启动项目上跑通，并确认 `plan` 不再依赖手工先改 `大纲/总纲.md`。

## 结论
- 结论：`通过（冷启动 plan 可用，1-3 章链路跑通）`
- 首轮 `plan` 已在 bootstrap 后直接完成，不再需要手工补写 `总纲.md`。
- `write` 第 1、2 章首次通过；第 3 章第一次尝试因 `continuity-review` 收到截断 JSON 失败，第二次重试后通过。
- `review chapter_range=1-3` 已完成，`blocking=false`。

## 冷启动链路结果
1. `POST /api/project/bootstrap` 成功初始化项目。
2. bootstrap 后默认已存在：
   - `.webnovel/planning-profile.json`
   - `大纲/总纲.md`
   - `planning.project_info`
3. bootstrap 返回的 `planning_profile.readiness.ok = true`，且 `source_order` 为：
   - `.webnovel/planning-profile.json`
   - `state.json planning.project_info`
   - `大纲/总纲.md`
4. `plan volume=1` 直接成功：
   - 状态：`completed`
   - 写回文件：`大纲/volume-01-plan.md`
   - `state.json` 中 `planning.volume_plans.1` 已落盘

## 写作与回归结果

### 章节链路
- `write chapter=1`：通过
- `write chapter=2`：通过
- `write chapter=3`：首次失败，重试后通过
- `review chapter_range=1-3`：通过

### 当前落盘状态
- `state.json`
  - `current_chapter = 3`
  - `total_words = 11583`
  - `progress.volumes_planned` 已包含卷 1
- 正文文件：3 章
- 摘要文件：3 章
- `大纲/volume-01-plan.md` 已生成并包含 50 章节拍

### 结构化同步
- `plan` 完成后已同步：
  - `设定集/世界观.md`
  - `设定集/力量体系.md`
  - `设定集/主角卡.md`
  - `设定集/金手指设计.md`
- `write chapter=3` 的 `data-sync` 已记录：
  - `Structured settings synced`
  - `Narrative state synced`
- `state.json` 中已沉淀 chapter 1-3 的 `structured_settings`、`world_settings`、`review_checkpoints`

## 1-3 章 review 摘要
- `blocking = false`
- `can_proceed = true`
- `severity_counts`
  - `medium = 7`
  - `low = 7`

本轮 1-3 章的主要风险集中在：
- 预警来源同源/异源仍需阶段性标签
- `优先弃后` 规则的适用范围需要进一步钉牢
- Chapter 3 章末切向 `B1 / 封存柜47` 的物理过渡仍需补桥
- `不要信自己的笔迹` 已起线，但还需要更客观的外部旁证

这些属于内容层连续性和后续章节承接问题，不再是第三阶段要解决的 `plan` 冷启动阻断。

## 残余问题
- Chapter 3 首次尝试失败码为：
  - `INVALID_STEP_OUTPUT`
  - `parse_stage = json_truncated`
  - 触发步骤：`continuity-review`
- 第二次重试后同一章节通过，说明当前主阻断已从“冷启动 plan 不可用”转移到“个别审查步骤仍可能收到截断输出”的稳定性问题。

## 验收判断
- 第三阶段的核心目标已完成：
  - `plan` 冷启动可用
  - bootstrap 后无需手工先改 `总纲.md`
  - 1-3 章真实链路可跑通
- 下一阶段应优先处理：
  - 审查步骤 `INVALID_STEP_OUTPUT/json_truncated` 的重试与容错
  - 1-3 章 review 中列出的 continuity / consistency 内容问题
