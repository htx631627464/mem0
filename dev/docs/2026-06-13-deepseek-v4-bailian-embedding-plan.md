# DeepSeek V4 + 百炼 Embedding Self-Hosted Server 改造实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `server/` 的 LLM 切换为 DeepSeek V4，Embedding 切换为阿里云百炼 `text-embedding-v4`，并保持 pgvector 默认维度 `1536` 可用。

**Architecture:** 保留 `mem0` 已有的 `deepseek` provider，不在库内新增 provider；仅在 `server/` 层扩展 bundled provider 白名单、补齐环境变量驱动的默认配置，并让 embedder 通过 OpenAI-compatible endpoint 接入百炼。

**Tech Stack:** Python, FastAPI, Docker Compose, PostgreSQL/pgvector, DeepSeek API, DashScope OpenAI-compatible Embedding API.

---

## File Structure

- `server/main.py`
  - 调整 bundled provider 白名单
  - 增加 DeepSeek / DashScope 环境变量读取
  - 重构 `DEFAULT_CONFIG` 生成逻辑
- `server/.env.example`
  - 增加 DeepSeek 与百炼相关变量
- `server/docker-compose.yaml`
  - 将新环境变量透传到 `mem0` 服务
- `server/tests/test_server_config.py` *(新增)*
  - 验证默认配置构建、provider 选择、维度默认值

## Bite-Sized Task Granularity

每个 step 控制在 2-5 分钟内完成；涉及代码修改时给出可直接替换的代码块。

---

### Task 1: 增加 server 配置构建单测

**Files:**
- Create: `server/tests/test_server_config.py`
- Modify: `server/main.py`

- [x] **Step 1: 创建最小测试文件**

```python
# server/tests/test_server_config.py
from __future__ import annotations

import importlib
import os


def _reload_main_with_env(env: dict[str, str]):
    for key in [
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_EMBEDDING_BASE_URL",
        "MEM0_DEFAULT_EMBEDDING_MODEL",
        "MEM0_DEFAULT_EMBEDDING_DIMS",
    ]:
        os.environ.pop(key, None)

    os.environ.update(env)
    import server.main as main
    importlib.reload(main)
    return main


def test_default_config_uses_deepseek_when_key_present():
    main = _reload_main_with_env({
        "DEEPSEEK_API_KEY": "sk-deepseek",
        "DASHSCOPE_API_KEY": "sk-dashscope",
    })

    config = main.DEFAULT_CONFIG
    assert config["llm"]["provider"] == "deepseek"
    assert config["llm"]["config"]["model"] == "deepseek-v4-flash"
    assert config["embedder"]["provider"] == "openai"
    assert config["embedder"]["config"]["model"] == "text-embedding-v4"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 1536


def test_default_config_fallback_to_openai_when_deepseek_missing():
    main = _reload_main_with_env({
        "OPENAI_API_KEY": "sk-openai",
    })

    config = main.DEFAULT_CONFIG
    assert config["llm"]["provider"] == "openai"
    assert config["embedder"]["provider"] == "openai"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 1536


def test_embedding_dims_can_be_overridden():
    main = _reload_main_with_env({
        "DEEPSEEK_API_KEY": "sk-deepseek",
        "DASHSCOPE_API_KEY": "sk-dashscope",
        "MEM0_DEFAULT_EMBEDDING_DIMS": "1024",
    })

    config = main.DEFAULT_CONFIG
    assert config["vector_store"]["config"]["embedding_model_dims"] == 1024
```

- [x] **Step 2: 运行测试确认当前失败**

Run:

```bash
cd server
python -m pytest tests/test_server_config.py -v
```

Expected: FAIL（当前 `main.py` 尚未实现新的默认配置逻辑）。

- [x] **Step 3: 在 `server/main.py` 增加测试入口保护**

```python
# server/main.py 顶部附近
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [x] **Step 4: 运行测试确认语法通过**

Run:

```bash
cd server
python -m pytest tests/test_server_config.py -v
```

Expected: 仍 FAIL，但文件可被 pytest 正常收集。

- [x] **Step 5: 提交测试骨架**

```bash
git add server/tests/test_server_config.py server/main.py
git commit -m "test(server): add config smoke tests for DeepSeek + Bailian design"
```

---

### Task 2: 实现 server 默认配置与白名单改造

**Files:**
- Modify: `server/main.py`

- [x] **Step 1: 扩展 bundled providers**

```python
# server/main.py:60
BUNDLED_LLM_PROVIDERS = ("openai", "anthropic", "gemini", "deepseek")
```

- [x] **Step 2: 增加环境变量读取**

```python
# server/main.py:113-117 附近
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
DASHSCOPE_EMBEDDING_BASE_URL = os.environ.get(
    "DASHSCOPE_EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MEM0_DEFAULT_EMBEDDING_MODEL = os.environ.get("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-v4")
MEM0_DEFAULT_EMBEDDING_DIMS = int(os.environ.get("MEM0_DEFAULT_EMBEDDING_DIMS", "1536"))
```

- [x] **Step 3: 替换默认配置构建逻辑**

```python
# server/main.py:118-137
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

- [x] **Step 4: 保持 config redaction 不泄露敏感字段**

Run:

```bash
cd server
python -m pytest tests/test_server_config.py -v
```

Expected: PASS。

- [x] **Step 5: 提交实现**

```bash
git add server/main.py
git commit -m "feat(server): switch default LLM to DeepSeek and embedder to DashScope-compatible OpenAI"
```

---

### Task 3: 更新环境变量模板与 Compose 配置

**Files:**
- Modify: `server/.env.example`
- Modify: `server/docker-compose.yaml`

- [x] **Step 1: 更新 `.env.example`**

```env
# DeepSeek LLM
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com

# DashScope Embedding (阿里云百炼)
DASHSCOPE_API_KEY=
DASHSCOPE_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MEM0_DEFAULT_EMBEDDING_MODEL=text-embedding-v4
MEM0_DEFAULT_EMBEDDING_DIMS=1536

# Optional fallback
OPENAI_API_KEY=
```

- [x] **Step 2: 在 `docker-compose.yaml` 中透传变量**

```yaml
# server/docker-compose.yaml mem0 service environment
environment:
  - PYTHONDONTWRITEBYTECODE=1
  - PYTHONUNBUFFERED=1
  - PYTHONPATH=
  - DASHBOARD_URL=http://localhost:3000
  - APP_DB_NAME=mem0_app
  - JWT_SECRET=${JWT_SECRET}
  - AUTH_DISABLED=${AUTH_DISABLED:-false}
  - MEM0_TELEMETRY=${MEM0_TELEMETRY:-true}
  - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
  - DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-deepseek-v4-flash}
  - DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-https://api.deepseek.com}
  - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-}
  - DASHSCOPE_EMBEDDING_BASE_URL=${DASHSCOPE_EMBEDDING_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}
  - MEM0_DEFAULT_EMBEDDING_MODEL=${MEM0_DEFAULT_EMBEDDING_MODEL:-text-embedding-v4}
  - MEM0_DEFAULT_EMBEDDING_DIMS=${MEM0_DEFAULT_EMBEDDING_DIMS:-1536}
  - OPENAI_API_KEY=${OPENAI_API_KEY:-}
```

- [x] **Step 3: 本地检查 compose 语法**

Run:

```bash
cd server
docker compose config -q
```

Expected: 无报错输出。

- [x] **Step 4: 提交配置变更**

```bash
git add server/.env.example server/docker-compose.yaml
git commit -m "docs(server): expose DeepSeek and DashScope env config"
```

---

### Task 4: 本地验证与 lint

**Files:**
- No new files
- Verify: `server/main.py`, `server/tests/test_server_config.py`

- [x] **Step 1: 运行单测**

Run:

```bash
cd server
python -m pytest tests/test_server_config.py -v
```

Expected: PASS。

- [x] **Step 2: 运行 server lint（ruff）**

Run:

```bash
cd server
ruff check .
```

Expected: 无 error。

- [x] **Step 3: 检查默认配置输出**

Run:

```bash
cd server
python - <<'PY'
import importlib, os
os.environ.update({
    "DEEPSEEK_API_KEY": "sk-test",
    "DASHSCOPE_API_KEY": "sk-test",
})
import server.main as main
importlib.reload(main)
print(main.DEFAULT_CONFIG)
PY
```

Expected:
- `llm.provider == "deepseek"`
- `embedder.config.model == "text-embedding-v4"`
- `vector_store.config.embedding_model_dims == 1536`

- [x] **Step 4: 提交验证结果说明（可选）**

```bash
git add dev/docs/2026-06-13-deepseek-v4-bailian-embedding-plan.md
git commit -m "docs(plan): add DeepSeek V4 + Bailian embedding implementation plan"
```

---

## Verification Matrix

1. `GET /configure/providers` → `llm` 列表包含 `deepseek`
2. `GET /configure` → `llm.provider == deepseek`
3. `GET /configure` → `embedder.config.model == text-embedding-v4`
4. `POST /memories` → 写入成功
5. `POST /search` → 返回结果合理

## Risks & Mitigations

| 风险 | 处理方式 |
|------|----------|
| `top_k` 不被 DeepSeek 完整支持 | 先验证当前行为；必要时在 server/provider 层过滤 |
| thinking 模式未自动开启 | 先以默认行为上线；后续再评估是否映射 `thinking` |
| embedding 维度漂移 | 强制默认 `1536`，并通过环境变量显式覆盖 |
