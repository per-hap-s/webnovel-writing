# Dashboard API 两章真实测试报告

## 基本信息
- 测试日期：2026-03-16
- 测试模式：真实 API
- 主链路：Dashboard API
- 非目标链路：CLI
- 测试项目目录：`D:\CodexProjects\NovelTest-2Ch`
- 书名：`《夜雨城回档人》`
- 题材：`都市异能`
- 测试目标：验证 `write` 逐章审批回写闭环在真实后端下能否稳定完成前 2 章，并确认正文、摘要、章节索引、质量指标、状态文件保持一致。

## 历史说明

本文档记录的是第三阶段修复前的真实基线。当前后续验收口径已调整为“首轮 `plan` 冷启动可用”：

- bootstrap 后不再要求先手工补写 `大纲/总纲.md`
- 首轮 `plan` 如被输入缺失阻断，应返回 `PLAN_INPUT_BLOCKED`，而不是表面 `completed`

## 测试环境
- 仓库根目录：`D:\CodexProjects\Project1\webnovel-writer\webnovel-writer`
- Python：`D:\CodexProjects\Project1\webnovel-writer\.venv\Scripts\python.exe`
- 独立 Dashboard 实例：`http://127.0.0.1:8766`
- 隔离目的：避开已有 `8765` 实例，避免污染其他测试数据
- 运行日志：
  - `D:\CodexProjects\NovelTest-2Ch\dashboard-8766.out.log`
  - `D:\CodexProjects\NovelTest-2Ch\dashboard-8766.err.log`

## 环境连通性确认
- `GET /api/llm/status`
  - 状态：`connected`
  - provider：`openai-compatible`
  - model：`gpt-5.4`
  - base_url：`http://127.0.0.1:8317/v1`
- `GET /api/rag/status`
  - 状态：`connected`

结论：本轮进入真实写作阶段前，写作模型与 RAG 均已联通。

## 测试范围
- 本轮重点验证：
  - 项目初始化
  - 单章 `write` 任务完整编排
  - 人工审批关卡
  - 审批后 `data-sync`
  - 正文 / 摘要 / 章节索引 / 质量指标 / 状态文件一致性
- 本轮不作为通过前提的内容：
  - `plan` 首次规划稳定性
  - `resume` 中断恢复
  - 范围 `review`

## 前置处理
1. 使用 `POST /api/project/bootstrap` 成功初始化测试项目。
2. 初次 `plan` 因 `大纲/总纲.md` 过空而无法产出有效规划。
3. 手工补充 `D:\CodexProjects\NovelTest-2Ch\大纲\总纲.md` 以提供真实写作可消费的基础上下文。
4. 之后 `plan` 不再立即阻断，但仍存在真实上游长时间卡住现象。

说明：由于本轮目标是验证两章真实写作闭环，且 `plan` 阻塞表现更接近上游响应稳定性问题，因此后续继续对 `write` 主链做真实验收。

## 执行记录

### Chapter 1
- 任务 ID：`6cfd18cab20a45b7b36af1af26db46ea`
- 请求参数：
  - `chapter=1`
  - `mode=standard`
  - `require_manual_approval=true`
- 实际执行链路：
  - `context`
  - `draft`
  - `consistency-review`
  - `continuity-review`
  - `ooc-review`
  - `review-summary`
  - `polish`
  - `approval-gate`
  - `data-sync`
- 关键观察：
  - 任务先停在 `awaiting_writeback_approval`
  - 审批前 `GET /api/chapters` 为空
  - 审批后任务恢复，仅执行后半段写回
  - 最终状态为 `completed`

#### Chapter 1 结果
- 正文已落盘：`D:\CodexProjects\NovelTest-2Ch\正文\第0001章.md`
- 摘要已落盘：`D:\CodexProjects\NovelTest-2Ch\.webnovel\summaries\ch0001.md`
- 章节索引已更新：`/api/chapters` 出现 chapter 1
- 质量指标已更新：`/api/review-metrics` 出现 1-1 单章记录
- 词数：`4279`
- 质量总分：`92.67`
- `review-summary` 结论：`blocking=false`

#### Chapter 1 内容验收
- 已明确落地世界异常入口
- 已明确写出回档能力
- 已明确写出记忆代价
- 已留下下一章钩子

正文可直接定位到的关键信息：
- `第1章 暴雨回档`
- `不是头疼，不是疲惫，是他真的少了一段记忆。`
- `那辆黑色面包车`
- `别再死第三次`

### Chapter 2
- 任务 ID：`03616bef138846359204fe88d31ce1f6`
- 请求参数：
  - `chapter=2`
  - `mode=standard`
  - `require_manual_approval=true`
- 实际执行链路：
  - `context`
  - `draft`
  - `consistency-review`
  - `continuity-review`
  - `ooc-review`
  - `review-summary`
  - `polish`
  - `approval-gate`
  - `data-sync`
- 关键观察：
  - 同样先停在 `awaiting_writeback_approval`
  - `review-summary` 无 hard blocking
  - 审批后快速进入 `data-sync`
  - 最终状态为 `completed`

#### Chapter 2 结果
- 正文已落盘：`D:\CodexProjects\NovelTest-2Ch\正文\第0002章.md`
- 摘要已落盘：`D:\CodexProjects\NovelTest-2Ch\.webnovel\summaries\ch0002.md`
- 章节索引已更新：`/api/chapters` 出现 chapter 2
- 质量指标已更新：`/api/review-metrics` 出现 2-2 单章记录
- 词数：`4072`
- 质量总分：`90.67`
- `review-summary` 结论：`blocking=false`

#### Chapter 2 内容验收
- 已接上第 1 章的“第三次回档警告”
- 已出现首次主动利用回档翻盘
- 已拿到可验证收益
- 已获得后续调查线索

正文可直接定位到的关键信息：
- `再来，同一事件的第三次回档会出问题。`
- `他没有回头。现在最重要的是把收益拿到手。`
- `异常观察点临时巡查时间：22:20。`
- `这条线索，能继续往下追了。`
- `想活，就别把那份排班单交给调查局。`
- `他翻盘了。`

## 落盘一致性核对

### 正文文件
- `D:\CodexProjects\NovelTest-2Ch\正文\第0001章.md`
- `D:\CodexProjects\NovelTest-2Ch\正文\第0002章.md`

### 摘要文件
- `D:\CodexProjects\NovelTest-2Ch\.webnovel\summaries\ch0001.md`
- `D:\CodexProjects\NovelTest-2Ch\.webnovel\summaries\ch0002.md`

### 章节索引
- `/api/chapters` 返回 2 条记录
- chapter 1 `word_count=4279`
- chapter 2 `word_count=4072`

### 质量指标
- `/api/review-metrics` 返回 2 条单章记录
- chapter 1：`overall_score=92.67`
- chapter 2：`overall_score=90.67`

### 项目状态
- `D:\CodexProjects\NovelTest-2Ch\.webnovel\state.json`
- `current_chapter=2`

结论：正文、摘要、索引、质量指标、状态文件在本轮两章测试中已对齐。

## 通过项
- 真实 API 模式下，`write` 任务可逐章执行
- 每章都先进入人工审批点，而不是直接写回
- 审批后 `data-sync` 能完成真实落盘
- `/api/chapters` 不再为空，且词数大于 0
- `/api/review-metrics` 在章节成功落盘后出现对应记录
- `state.json` 已推进到第 2 章
- 两章正文内容均满足本轮最低业务验收点

## 发现的问题

### 1. `plan` 仍未达到稳定可验收状态
- 现象：
  - 初次规划对空总纲敏感
  - 补完总纲后不再立即阻断，但仍可能长时间停留在运行中
- 影响：
  - 当前无法把“首次 `plan` 成功”纳入本轮通过项
- 判定：
  - 属于残余阻断问题，但不影响本轮两章 `write` 闭环通过

### 2. Chapter 2 仍有中等严重度内容问题，但不阻断写作闭环
- 典型问题：
  - 章尾“妹妹买药信息”表现为事实摇摆，读者容易误读为设定冲突，而不是主角记忆受损
  - 第二轮行动的时间锚点不够显式
  - 维修通道的空间关系说明偏弱
  - “别再死第三次”与后续预警来源仍偏悬空
- 影响：
  - 不影响系统闭环
  - 会影响后续连贯性与阅读清晰度

## 本轮结论
- 结论日期：2026-03-16
- 结论：`通过（限两章 write 闭环）`

本轮真实测试已经确认，在 API 模式下，Dashboard 写作主链可以稳定完成前 2 章的逐章审批回写闭环。`write` 的任务编排、审批暂停、写回落盘、章节索引更新、质量指标固化、状态文件推进均已真实跑通。

但项目尚未达到“完整主链全部稳定”的最终标准，主要残余问题仍在 `plan` 的真实稳定性，以及第 2 章暴露的若干非阻断内容清晰度问题。若进入下一轮，建议优先继续做：
- `plan` 首次成功稳定性复验
- 第 3 章真实续写
- `review chapter_range=1-3`
- 中断恢复与 `resume` 复验
