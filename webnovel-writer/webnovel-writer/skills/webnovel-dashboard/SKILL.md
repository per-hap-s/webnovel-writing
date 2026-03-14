---
name: webnovel-dashboard
description: 启动可视化小说管理面板，用于查看项目状态、发起任务，并在面板中维护写作模型与 RAG API 配置。
---

# Webnovel Dashboard

## 目标

在本地启动一个 Web 面板，用于查看和管理当前小说项目的：

- 创作进度与 Strand 节奏分布
- 设定词典（角色、地点、势力等实体）
- 关系图谱
- 章节与大纲内容浏览
- 追读力分析数据
- 工作流任务状态与审批状态
- 写作模型 API 与 RAG API 配置

面板通过 `watchdog` 监听 `.webnovel/` 目录变更并实时刷新。

## 执行步骤

### Step 0：环境确认

```bash
export WORKSPACE_ROOT="${WEBNOVEL_WORKSPACE_ROOT:-$PWD}"

if [ -z "${WEBNOVEL_APP_ROOT}" ] || [ ! -d "${WEBNOVEL_APP_ROOT}/dashboard" ]; then
  echo "ERROR: 未找到 dashboard 模块: ${WEBNOVEL_APP_ROOT}/dashboard" >&2
  exit 1
fi
export DASHBOARD_DIR="${WEBNOVEL_APP_ROOT}/dashboard"
```

### Step 1：安装依赖（首次）

```bash
python -m pip install -r "${DASHBOARD_DIR}/requirements.txt" --quiet
```

### Step 2：解析项目根目录并准备 Python 模块路径

```bash
export SCRIPTS_DIR="${WEBNOVEL_APP_ROOT}/scripts"
export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
echo "项目路径: ${PROJECT_ROOT}"

if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="${WEBNOVEL_APP_ROOT}:${PYTHONPATH}"
else
  export PYTHONPATH="${WEBNOVEL_APP_ROOT}"
fi

if [ ! -f "${DASHBOARD_DIR}/frontend/dist/index.html" ]; then
  echo "ERROR: 缺少前端构建产物 ${DASHBOARD_DIR}/frontend/dist/index.html" >&2
  echo "请重新安装插件或联系维护者修复发布包。" >&2
  exit 1
fi
```

### Step 3：启动 Dashboard

```bash
python -m dashboard.server --project-root "${PROJECT_ROOT}"
```

启动后会自动打开浏览器访问 `http://127.0.0.1:8765`。

如果不需要自动打开浏览器，使用：

```bash
python -m dashboard.server --project-root "${PROJECT_ROOT}" --no-browser
```

## 当前能力

Dashboard 当前同时包含查看能力和控制能力：

- 查看项目概览、实体、关系、章节、文件、质量数据
- 创建项目
- 发起 `init / plan / write / review / resume` 任务
- 重试任务、批准回写、拒绝回写
- 在 `总览 -> API 接入设置` 中保存写作模型 API 与 RAG API 配置

## 注意事项

- Dashboard 不再是“纯只读面板”。当前同时包含 GET 查询接口和 POST 控制接口。
- API 配置保存位置为项目根目录 `.env`。
- 文件读取仍然严格限制在 `PROJECT_ROOT` 下的 `正文`、`大纲`、`设定集` 范围内，防止路径穿越。
- 如需自定义端口，添加 `--port 9000` 参数。
