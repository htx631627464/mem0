from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config_builder import build_default_config

_ENV_KEYS = [
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_BASE_URL",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_EMBEDDING_BASE_URL",
    "MEM0_DEFAULT_EMBEDDING_MODEL",
    "MEM0_DEFAULT_EMBEDDING_DIMS",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_COLLECTION_NAME",
    "HISTORY_DB_PATH",
    "MEM0_DEFAULT_LLM_MODEL",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# 现有 OpenAI 配置行为（原 main.py DEFAULT_CONFIG 逻辑）
# 这些测试验证 config_builder.py 正确复现了原始行为
# ---------------------------------------------------------------------------


def test_openai_provider_when_only_openai_key_present(monkeypatch: pytest.MonkeyPatch):
    """仅有 OPENAI_API_KEY 时，LLM 和 embedder 都使用 openai。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = build_default_config()

    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["api_key"] == "sk-openai"
    assert config["llm"]["config"]["model"] == "gpt-4.1-nano-2025-04-14"
    assert config["llm"]["config"]["temperature"] == 0.2
    assert config["embedder"]["provider"] == "openai"
    assert config["embedder"]["config"]["api_key"] == "sk-openai"
    assert config["embedder"]["config"]["model"] == "text-embedding-3-small"


def test_no_keys_returns_none_api_keys(monkeypatch: pytest.MonkeyPatch):
    """无任何 API key 时，provider 仍为 openai，api_key 为 None。"""
    config = build_default_config()

    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["api_key"] is None
    assert config["embedder"]["config"]["api_key"] is None


def test_postgres_config_defaults(monkeypatch: pytest.MonkeyPatch):
    """PostgreSQL 默认配置验证。"""
    config = build_default_config()

    vs = config["vector_store"]["config"]
    assert vs["host"] == "postgres"
    assert vs["port"] == 5432
    assert vs["dbname"] == "postgres"
    assert vs["user"] == "postgres"
    assert vs["password"] == "postgres"
    assert vs["collection_name"] == "memories"


def test_postgres_config_override(monkeypatch: pytest.MonkeyPatch):
    """PostgreSQL 环境变量覆盖验证。"""
    monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "mydb")
    monkeypatch.setenv("POSTGRES_USER", "myuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_COLLECTION_NAME", "my_memories")

    config = build_default_config()

    vs = config["vector_store"]["config"]
    assert vs["host"] == "db.example.com"
    assert vs["port"] == 5433
    assert vs["dbname"] == "mydb"
    assert vs["user"] == "myuser"
    assert vs["password"] == "secret"
    assert vs["collection_name"] == "my_memories"


def test_custom_llm_model(monkeypatch: pytest.MonkeyPatch):
    """自定义 LLM 模型覆盖。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("MEM0_DEFAULT_LLM_MODEL", "gpt-4o")

    config = build_default_config()

    assert config["llm"]["config"]["model"] == "gpt-4o"


def test_custom_embedder_model(monkeypatch: pytest.MonkeyPatch):
    """自定义 embedder 模型覆盖。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-3-large")

    config = build_default_config()

    assert config["embedder"]["config"]["model"] == "text-embedding-3-large"


def test_default_history_db_path(monkeypatch: pytest.MonkeyPatch):
    """默认 history_db_path 值验证。"""
    config = build_default_config()

    assert config["history_db_path"] == "/app/history/history.db"


def test_custom_history_db_path(monkeypatch: pytest.MonkeyPatch):
    """自定义 history_db_path 覆盖。"""
    monkeypatch.setenv("HISTORY_DB_PATH", "/custom/path/history.db")

    config = build_default_config()

    assert config["history_db_path"] == "/custom/path/history.db"


def test_default_embedding_dims(monkeypatch: pytest.MonkeyPatch):
    """默认 embedding_model_dims 为 1536。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = build_default_config()

    assert config["vector_store"]["config"]["embedding_model_dims"] == 1536


def test_embedding_dims_override(monkeypatch: pytest.MonkeyPatch):
    """自定义 embedding_model_dims 覆盖。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("MEM0_DEFAULT_EMBEDDING_DIMS", "1024")

    config = build_default_config()

    assert config["vector_store"]["config"]["embedding_model_dims"] == 1024


def test_config_structure_completeness(monkeypatch: pytest.MonkeyPatch):
    """验证返回的 dict 包含所有必需的顶层 key。"""
    config = build_default_config()

    assert "version" in config
    assert "vector_store" in config
    assert "llm" in config
    assert "embedder" in config
    assert "history_db_path" in config
    assert config["version"] == "v1.1"


def test_explicit_env_dict():
    """传入自定义 env dict 时正常工作。"""
    env = {"OPENAI_API_KEY": "sk-test"}
    config = build_default_config(env)

    assert config["llm"]["config"]["api_key"] == "sk-test"


# ---------------------------------------------------------------------------
# DeepSeek + Dashscope 新增功能
# 这些测试验证 config_builder.py 中新增的 DeepSeek/Dashscope 支持
# ---------------------------------------------------------------------------


def test_deepseek_when_both_keys_present(monkeypatch: pytest.MonkeyPatch):
    """同时有 DEEPSEEK_API_KEY 和 DASHSCOPE_API_KEY 时使用 deepseek provider。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")

    config = build_default_config()

    assert config["llm"]["provider"] == "deepseek"
    assert config["llm"]["config"]["model"] == "deepseek-v4-flash"
    assert config["llm"]["config"]["api_key"] == "sk-deepseek"
    assert config["llm"]["config"]["deepseek_base_url"] == "https://api.deepseek.com"
    assert config["embedder"]["provider"] == "openai"
    assert config["embedder"]["config"]["model"] == "text-embedding-v4"
    assert config["embedder"]["config"]["api_key"] == "sk-dashscope"
    assert config["embedder"]["config"]["openai_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config["vector_store"]["config"]["embedding_model_dims"] == 1536


def test_deepseek_without_dashscope_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch):
    """仅有 DEEPSEEK_API_KEY 无 DASHSCOPE_API_KEY 时回退到 openai。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = build_default_config()

    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["api_key"] == "sk-openai"
    assert config["embedder"]["provider"] == "openai"


def test_dashscope_without_deepseek_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch):
    """仅有 DASHSCOPE_API_KEY 无 DEEPSEEK_API_KEY 时回退到 openai。"""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = build_default_config()

    assert config["llm"]["provider"] == "openai"
    assert config["llm"]["config"]["api_key"] == "sk-openai"
    assert config["embedder"]["provider"] == "openai"
    assert config["embedder"]["config"]["api_key"] == "sk-openai"


def test_both_keys_present_deepseek_wins_over_openai(monkeypatch: pytest.MonkeyPatch):
    """三个 key 都存在时，deepseek + dashscope 优先于 openai。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    config = build_default_config()

    assert config["llm"]["provider"] == "deepseek"
    assert config["llm"]["config"]["api_key"] == "sk-deepseek"
    assert config["embedder"]["config"]["api_key"] == "sk-dashscope"


def test_deepseek_custom_model(monkeypatch: pytest.MonkeyPatch):
    """自定义 DEEPSEEK_MODEL 覆盖默认模型。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v3")

    config = build_default_config()

    assert config["llm"]["config"]["model"] == "deepseek-v3"


def test_explicit_env_dict_deepseek():
    """传入自定义 env dict 时 deepseek 配置正常工作。"""
    env = {"DEEPSEEK_API_KEY": "sk-ds", "DASHSCOPE_API_KEY": "sk-ds-embed"}
    config = build_default_config(env)

    assert config["llm"]["provider"] == "deepseek"
    assert config["embedder"]["config"]["api_key"] == "sk-ds-embed"


def test_deepseek_base_url_and_dashscope_base_url(monkeypatch: pytest.MonkeyPatch):
    """DEEPSEEK_BASE_URL 和 DASHSCOPE_EMBEDDING_BASE_URL 正确透传到配置。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("DASHSCOPE_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    config = build_default_config()

    assert config["llm"]["config"]["deepseek_base_url"] == "https://api.deepseek.com/v1"
    assert config["embedder"]["config"]["openai_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_deepseek_embedder_model_override(monkeypatch: pytest.MonkeyPatch):
    """DeepSeek 路径下 MEM0_DEFAULT_EMBEDDING_MODEL 可覆盖默认 embedder 模型。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-v3")

    config = build_default_config()

    assert config["embedder"]["config"]["model"] == "text-embedding-v3"


# ---------------------------------------------------------------------------
# 边界条件测试
# ---------------------------------------------------------------------------


def test_non_numeric_embedding_dims_raises(monkeypatch: pytest.MonkeyPatch):
    """MEM0_DEFAULT_EMBEDDING_DIMS 为非数字字符串时应抛出 ValueError。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("MEM0_DEFAULT_EMBEDDING_DIMS", "not-a-number")

    with pytest.raises(ValueError, match="invalid literal"):
        build_default_config()


def test_empty_embedding_dims_raises(monkeypatch: pytest.MonkeyPatch):
    """MEM0_DEFAULT_EMBEDDING_DIMS 为空字符串时应抛出 ValueError。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("MEM0_DEFAULT_EMBEDDING_DIMS", "")

    with pytest.raises(ValueError):
        build_default_config()


# ---------------------------------------------------------------------------
# 端到端测试：验证 config dict → Memory.from_config() 链路不崩溃
# ---------------------------------------------------------------------------


def test_from_config_deepseek_e2e(monkeypatch: pytest.MonkeyPatch):
    """验证 DeepSeek 路径下 build_default_config() → Memory.from_config() 不抛异常。

    Mock 外部依赖（LLM client、embedder、vector store、SQLite），
    仅验证配置解析和对象构建链路。
    """
    from unittest.mock import MagicMock, patch

    from mem0 import Memory

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    config = build_default_config()

    # 验证 config dict 中 key 名正确
    assert "deepseek_base_url" in config["llm"]["config"]
    assert "base_url" not in config["llm"]["config"]

    with (
        patch("mem0.utils.factory.LlmFactory.create") as mock_llm,
        patch("mem0.utils.factory.EmbedderFactory.create") as mock_embedder,
        patch("mem0.utils.factory.VectorStoreFactory.create") as mock_vs,
        patch("mem0.memory.main.SQLiteManager") as mock_sqlite,
        patch("mem0.memory.main.MEM0_TELEMETRY", False),
    ):
        mock_llm.return_value = MagicMock()
        mock_embedder.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_sqlite.return_value = MagicMock()

        mem = Memory.from_config(config)

    assert mem.config.llm.provider == "deepseek"
    assert mem.config.embedder.provider == "openai"
    assert mem.config.llm.config["deepseek_base_url"] == "https://api.deepseek.com/v1"


def test_from_config_deepseek_default_base_url_e2e(monkeypatch: pytest.MonkeyPatch):
    """未设 DEEPSEEK_BASE_URL 时，默认值 https://api.deepseek.com 到达 DeepSeekLLM。"""
    from unittest.mock import MagicMock, patch

    from mem0 import Memory

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dashscope")

    config = build_default_config()

    assert config["llm"]["config"]["deepseek_base_url"] == "https://api.deepseek.com"
    assert config["embedder"]["config"]["openai_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    with (
        patch("mem0.utils.factory.LlmFactory.create") as mock_llm,
        patch("mem0.utils.factory.EmbedderFactory.create") as mock_embedder,
        patch("mem0.utils.factory.VectorStoreFactory.create") as mock_vs,
        patch("mem0.memory.main.SQLiteManager") as mock_sqlite,
        patch("mem0.memory.main.MEM0_TELEMETRY", False),
    ):
        mock_llm.return_value = MagicMock()
        mock_embedder.return_value = MagicMock()
        mock_vs.return_value = MagicMock()
        mock_sqlite.return_value = MagicMock()

        mem = Memory.from_config(config)

    assert mem.config.llm.provider == "deepseek"
    assert mem.config.llm.config["deepseek_base_url"] == "https://api.deepseek.com"
    assert mem.config.embedder.config["openai_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
