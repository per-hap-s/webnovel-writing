# RAG 与配置说明

## 推荐配置方式

当前推荐把配置统一放在项目根目录 `.env`，并优先通过 Dashboard 页面修改：

```text
总览 -> API 接入设置
```

这样做的好处是：

- 每本书单独管理，不容易串配置
- 修改后面板会立即刷新连接状态
- 后续任务直接复用同一套配置

## 面板内可修改的配置

### 写作模型 API

Dashboard 会把以下字段写入项目 `.env`：

```bash
WEBNOVEL_LLM_PROVIDER=openai-compatible
WEBNOVEL_LLM_BASE_URL=https://api.openai.com/v1
WEBNOVEL_LLM_MODEL=gpt-4.1-mini
WEBNOVEL_LLM_API_KEY=your_llm_api_key
```

页面对应字段：

- `Provider`
- `Base URL`
- `模型名称`
- `API Key`

补充说明：

- 留空 `API Key` 时，会保留当前已保存的 Key
- 兼容读取 `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_API_KEY`
- 如果未配置 API，但本机存在可用 `Codex CLI`，任务执行会自动回退到 CLI 模式

### RAG API

Dashboard 会把以下字段写入项目 `.env`：

```bash
WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1
WEBNOVEL_RAG_EMBED_MODEL=BAAI/bge-m3
WEBNOVEL_RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
WEBNOVEL_RAG_API_KEY=your_rag_api_key
```

页面对应字段：

- `Base URL`
- `Embedding 模型`
- `Rerank 模型`
- `API Key`

当前实现里，Embedding 和 Rerank 共用同一个 `WEBNOVEL_RAG_API_KEY`。

Dashboard 里的 RAG 状态也以真实探活结果为准：

- 只有探活返回 `connected` 时，界面才会显示“已连接”
- 仅“已配置”但探活失败、超时或未连通时，会显示“未连接”或“连接失败”，不会再按可用状态展示

## 面板后端接口

如果要从自定义脚本调用，而不是手工点界面，可使用：

- `POST /api/settings/llm`
- `POST /api/settings/rag`
- `GET /api/settings/llm`
- `GET /api/settings/rag`

保存位置都是项目根目录 `.env`。

## 运行时加载规则

推荐把“项目根目录 `.env`”当作唯一可信配置源。

当前行为可以概括为：

- Dashboard 设置页读取和保存时，优先围绕项目根目录 `.env`
- 若项目 `.env` 未提供 `WEBNOVEL_RAG_API_KEY`，Dashboard 运行时和 readonly audit 会回退读取应用根目录 `.env` 里的同名变量
- 任务执行阶段仍会尊重已显式导出的环境变量
- CLI 运行时会优先保留显式环境变量，再补充项目 `.env`

因此，最稳妥的做法仍然是：

1. 不要把不同项目共用同一组环境变量
2. 每个项目都维护自己的 `.env`
3. 尽量通过 Dashboard 的“API 接入设置”统一修改

## 最小配置示例

如果只配置 RAG：

```bash
WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1
WEBNOVEL_RAG_EMBED_MODEL=BAAI/bge-m3
WEBNOVEL_RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
WEBNOVEL_RAG_API_KEY=your_rag_api_key
```

如果同时配置写作模型和 RAG：

```bash
WEBNOVEL_LLM_PROVIDER=openai-compatible
WEBNOVEL_LLM_BASE_URL=https://api.openai.com/v1
WEBNOVEL_LLM_MODEL=gpt-4.1-mini
WEBNOVEL_LLM_API_KEY=your_llm_api_key

WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1
WEBNOVEL_RAG_EMBED_MODEL=BAAI/bge-m3
WEBNOVEL_RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
WEBNOVEL_RAG_API_KEY=your_rag_api_key
```

## 旧变量名说明

旧文档里曾使用：

```bash
EMBED_BASE_URL
EMBED_MODEL
EMBED_API_KEY
RERANK_BASE_URL
RERANK_MODEL
RERANK_API_KEY
```

当前面板写入与 Dashboard 运行时建议统一使用 `WEBNOVEL_LLM_*` 和 `WEBNOVEL_RAG_*`。
如果旧项目里还保留旧变量，建议逐步迁移，避免后续文档和界面对不上。
