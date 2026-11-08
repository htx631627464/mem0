# DeepSeek V4 + 百炼 Embedding Self-Hosted Server 改造设计

> **目标：** 将 `server/` 的 LLM 从 MiniMax Token Plan 切换到 DeepSeek V4，Embedding 从 OpenAI 切换到阿里云百炼 `text-embedding-v4`，Vector Store 继续使用 `pgvector`。

## 1. 背景与决策

### 1.1 为什么放弃 MiniMax Token Plan
- 用户确认 MiniMax Token Plan 的 API 不适合直接兼容当前计划用量。
- DeepSeek 官方提供标准 OpenAI-compatible Chat API，且 `mem0` 已内置 `deepseek` provider，改造成本更低。

### 1.2 为什么 Embedding 选百炼
- 阿里云百炼 `text-embedding-v4` 提供 OpenAI 兼容接口。
- 支持 `1536` 维度，可继续沿用现有 pgvector collection，避免维度迁移。
- 官方文档：`https://help.aliyun.com/zh/model-studio/developer-reference/text-embedding-api`

### 1.3 当前源码事实
- `mem0/utils/factory.py:50` 已注册 `deepseek` provider。
- `mem0/llms/deepseek.py:36-41` 默认模型 `deepseek-chat`，默认 base_url `https://api.deepseek.com`。
- `server/main.py:60` bundled providers 仅 `("openai", "anthropic", "gemini")`，未放行 `deepseek`。
- DeepSeek 官方文档明确 `deepseek-chat` / `deepseek-reasoner` 将于 **2026-07-24** 弃用，推荐 `deepseek-v4-flash` / `deepseek-v4-pro`。

## 2. 目标配置

| 组件 | Provider | Model / 参数 | 备注 |
|------|----------|--------------|------|
| LLM | `deepseek` | `deepseek-v4-flash`（默认）/ `deepseek-v4-pro` | 显式配置，不依赖 mem0 默认值 |
| Embedder | `openai`（实际接百炼） | `text-embedding-v4` | `openai_base_url` 指向百炼 OpenAI-compatible endpoint |
| Vector Store | `pgvector` | `embedding_model_dims=1536` | 继续沿用现有维度，避免迁移 |

## 3. 环境变量设计

```env
# DeepSeek LLM
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com

# DashScope Embedding (阿里云百炼)
DASHSCOPE_API_KEY=sk-xxx
DASHSCOPE_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MEM0_DEFAULT_EMBEDDING_MODEL=text-embedding-v4
MEM0_DEFAULT_EMBEDDING_DIMS=1536

# Fallback (可选)
OPENAI_API_KEY=sk-xxx
```

## 4. Server 侧改造点

### 4.1 扩展 bundled providers
**文件：** `server/main.py:60`

```python
# Before
BUNDLED_LLM_PROVIDERS = ("openai", "anthropic", "gemini")

# After
BUNDLED_LLM_PROVIDERS = ("openai", "anthropic", "gemini", "deepseek")
```

### 4.2 调整默认 config
**文件：** `server/main.py:118-137`

```python
# LLM
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# Embedding
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
DASHSCOPE_EMBEDDING_BASE_URL = os.environ.get(
    "DASHSCOPE_EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MEM0_DEFAULT_EMBEDDING_MODEL = os.environ.get("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-v4")
MEM0_DEFAULT_EMBEDDING_DIMS = int(os.environ.get("MEM0_DEFAULT_EMBEDDING_DIMS", "1536"))

DEFAULT_CONFIG = {
    "version": "v1.1",
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": POSTGRES_HOST,
            "port": int(POSTGRES_PORT),
            "dbname": POSTGRES_DB,
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "collection_name": POSTGRES_COLLECTION_NAME,
            "embedding_model_dims": MEM0_DEFAULT_EMBEDDING_DIMS,
        },
    },
    "llm": {
        "provider": "deepseek" if DEEPSEEK_API_KEY else "openai",
        "config": {
            "api_key": DEEPSEEK_API_KEY or OPENAI_API_KEY,
            "model": DEEPSEEK_MODEL if DEEPSEEK_API_KEY else DEFAULT_LLM_MODEL,
            "deepseek_base_url": DEEPSEEK_BASE_URL if DEEPSEEK_API_KEY else None,
            "temperature": 0.2,
        },
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "api_key": DASHSCOPE_API_KEY or OPENAI_API_KEY,
            "model": MEM0_DEFAULT_EMBEDDING_MODEL,
            "openai_base_url": DASHSCOPE_EMBEDDING_BASE_URL if DASHSCOPE_API_KEY else None,
        },
    },
    "history_db_path": HISTORY_DB_PATH,
}
```

### 4.3 更新 `.env.example`
**文件：** `server/.env.example`

新增 DeepSeek 与百炼相关变量，保留 `OPENAI_API_KEY` 作为 fallback。

### 4.4 更新 `docker-compose.yaml`
**文件：** `server/docker-compose.yaml`

将新环境变量透传到 `mem0` 容器。

## 5. 风险与回滚

| 风险 | 缓解措施 |
|------|----------|
| `deepseek-chat` 已弃用 | 必须显式设置 `DEEPSEEK_MODEL=deepseek-v4-flash` |
| thinking 模式未自动开启 | 当前先以默认行为验证，后续再考虑映射 `thinking` 参数 |
| `top_k` 可能不被 DeepSeek 支持 | 验证阶段观察，必要时在 provider 层过滤 |
| Embedding 维度不一致 | 默认 `1536`，显式配置 `MEM0_DEFAULT_EMBEDDING_DIMS` |

**回滚策略：**
- 删除 `DEEPSEEK_API_KEY` → 回落到 OpenAI LLM
- 删除 `DASHSCOPE_API_KEY` → 回落到 OpenAI Embedding
- 只要不改 `collection_name` 和维度，回滚是配置级别

## 6. 验证矩阵

1. `GET /configure/providers` → `llm` 列表包含 `deepseek`
2. `GET /configure` → `llm.provider == deepseek`，`embedder.config.model == text-embedding-v4`
3. `POST /memories` → 写入成功
4. `POST /search` → 返回结果合理
5. Dashboard `/dashboard/requests` → 可见 DeepSeek 调用日志

## 7. 后续事项

- [x] 实施 `server/` 代码改造
- [x] 更新 `.env.example` 与 `docker-compose.yaml`
- [ ] 在 hk-vps 远端部署并验证
- [ ] 考虑后续是否映射 DeepSeek thinking 模式
