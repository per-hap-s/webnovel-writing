# 项目结构与运维

## 目录层级

运行时建议统一使用这几个路径概念：

1. `WORKSPACE_ROOT`：你的工作区根目录。
2. `WORKSPACE_ROOT/.webnovel/`：工作区级指针与缓存目录。
3. `PROJECT_ROOT`：真实小说项目根目录，由 `webnovel init` 创建。
4. `PLUGIN_ROOT`：插件或仓库代码目录。

### Workspace 目录

```text
workspace-root/
├── .webnovel/
│   ├── current_project
│   └── settings.json
├── 小说A/
├── 小说B/
└── ...
```

### 小说项目目录

```text
project-root/
├── .webnovel/
├── 正文/
├── 大纲/
└── 设定集/
```

## 常用环境变量

```bash
export WORKSPACE_ROOT="${WORKSPACE_ROOT:-$PWD}"
export PLUGIN_ROOT="/path/to/webnovel-writer"
export SCRIPTS_DIR="${PLUGIN_ROOT}/scripts"
export PROJECT_ROOT="$(python "${SCRIPTS_DIR}/webnovel.py" --project-root "${WORKSPACE_ROOT}" where)"
```

## 常用运维命令

### 索引检查

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" index stats
```

### 状态报告

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" status -- --focus all
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" status -- --focus urgency
```

### RAG 检查

```bash
python "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" rag stats
```

### 测试入口

```bash
pwsh "${PLUGIN_ROOT}/scripts/run_tests.ps1" -Mode smoke
pwsh "${PLUGIN_ROOT}/scripts/run_tests.ps1" -Mode full
```

## Dashboard Frontend Artifact Maintenance

`dashboard/frontend/dist/` is the runtime static asset directory for the dashboard and remains committed in this project.

Rules:

- If `dashboard/frontend/src/` changes, run `npm run build` and commit the resulting `dist/` update in the same change.
- `dist/index.html` and `dist/assets/` must come from the same build output.
- Remove superseded hashed files from `dist/assets/` when a new build replaces them.
