# 桌面启动器入口 Dashboard API 两章真实浏览器测试报告

## 基本信息
- 测试日期：2026-03-16
- 测试模式：真实 API + 真实浏览器面板操作
- 测试目标：从桌面启动器入口开始，验证 `init -> API 接入设置 -> plan -> write 1 -> write 2` 两章冒烟链路
- 测试项目目录：`D:\CodexProjects\NovelTest-Launcher-2Ch`
- 书名：`《夜雨城回档人》`
- 题材：`都市异能`
- 结果结论：`阻断于 plan，未进入第 1 章写作`

## 历史说明

本文档保留第三阶段修复前的真实浏览器基线。后续桌面启动器链路的正式验收口径已改为：

- bootstrap 后默认引导到 `Planning Profile`
- `plan` 若因规划输入不足被阻断，任务状态必须为 `failed`
- 错误码固定为 `PLAN_INPUT_BLOCKED`，且不再写入空壳 `volume-01-plan.md`

## 执行记录
1. 清理了历史测试目录：
   - `D:\CodexProjects\NovelTest-3Ch`
   - `D:\CodexProjects\NovelTest-5Ch`
   - 新目录 `D:\CodexProjects\NovelTest-Launcher-2Ch`
2. 发现旧实例占用：
   - `8765` 被 `dashboard.server --project-root D:\CodexProjects\NovelTest-5Ch` 占用
   - `8766` 被 `dashboard.server --project-root D:\CodexProjects\NovelTest-2Ch` 占用
3. 关闭旧 Dashboard 进程后，清理完成；`NovelTest-2Ch` 也最终可删除。
4. 已从桌面快捷方式 `C:\Users\Administrator\Desktop\启动小说项目.lnk` 触发启动链路，并确认其入口目标为 `D:\CodexProjects\Project1\tools\Start-Webnovel-Writer.bat`。
5. 原生控制台菜单窗口无法稳定聚焦输入，随后改用同一启动器脚本的等价 `dashboard` 动作继续真实链路；项目标题和题材通过启动器原生输入框完成初始化。
6. Dashboard 在 `http://127.0.0.1:8765` 正常启动，浏览器页面中项目已加载为 `夜雨城回档人`。
7. 在页面 `API 接入设置` 中保存真实配置后，状态均显示已联通：
   - 写作模型：`API / gpt-5.4`
   - RAG：`BAAI/bge-m3`
8. 在页面创建 `plan volume=1 mode=standard` 任务。
9. `plan` 任务页面状态显示为 `已完成`，但步骤输出实际返回 `volume_plan.status = BLOCKED`，内容是“请先补齐总纲关键信息”的阻断模板，而不是可消费卷规划。
10. 按本轮执行规则，在 `plan` 未产出有效卷纲后停止，不继续创建 `write chapter=1` 和 `write chapter=2`。

## 页面与落盘结果
### 已成功完成
- 项目目录已初始化，存在：
  - `.webnovel/`
  - `正文/`
  - `大纲/`
  - `设定集/`
- 项目 `.env` 已由页面保存，包含真实 LLM 与 RAG 配置。
- `plan_input_health_checked` 事件已在任务详情页出现。
- `大纲/volume-01-plan.md` 已落盘。

### 未成功完成
- `plan` 未生成可消费的卷规划内容。
- `正文/` 目录下没有章节文件。
- `.webnovel/summaries/` 下没有章节摘要文件。
- 因 `plan` 阻断，本轮未进入 Chapter 1/2 写作审批链。

## 核心证据
### 任务页截图
- 页面截图：`D:\CodexProjects\Project1\webnovel-writer\webnovel-writer\output\playwright\dashboard-plan-blocked-20260316.png`

### 关键文件
- 总纲：`D:\CodexProjects\NovelTest-Launcher-2Ch\大纲\总纲.md`
- 卷规划写回文件：`D:\CodexProjects\NovelTest-Launcher-2Ch\大纲\volume-01-plan.md`
- 状态文件：`D:\CodexProjects\NovelTest-Launcher-2Ch\.webnovel\state.json`
- 页面保存后的配置：`D:\CodexProjects\NovelTest-Launcher-2Ch\.env`

### 关键现象
- `volume-01-plan.md` 仅写入：
  - `# Volume 1 Plan`
  - `Title: Volume 1`
- `state.json` 中 `planning.volume_plans.1.chapter_count = 0`
- 任务详情中的 LLM 结构化输出明确列出多项阻断字段，包括：
  - 卷 1 卷名为空
  - 卷 1 核心冲突为空
  - 卷 1 卷末高潮为空
  - 故事一句话为空
  - 主角信息为空
  - 核心设定为空
  - 能力代价为空
  - 主线目标与主要阻力为空
  - 主角当前欲望为空
  - 主角核心缺陷为空
  - 势力格局为空
  - 规则/体系为空
  - 关键伏笔为空
  - 主要角色信号缺失

## 结论
- 本轮真实浏览器测试已经确认：
  - 桌面启动器链路可进入 Dashboard。
  - 页面 API 设置保存与连通性显示正常。
  - `plan` 会进入真实模型调用并产生任务详情、事件流和写回副作用。
- 本轮同时确认一个主阻断缺陷：
  - 新项目冷启动后，当前初始化生成的 `总纲.md` 仍不足以支撑首次 `plan` 产出有效卷纲；任务虽然表面 `completed`，但实质结果为 `BLOCKED` 模板，不能继续消费到第 1 章写作。
- 因此，本轮两章真实冒烟测试未通过，阻断点为 `plan`，后续 `write` 链路未执行。
