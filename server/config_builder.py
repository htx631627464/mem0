"""Pure config builder — no server imports, no side effects."""

from __future__ import annotations

import os


def build_default_config(env: dict[str, str] | None = None) -> dict:
    """Build DEFAULT_CONFIG from environment variables.

    Pure function: reads only from *env* (defaults to ``os.environ``),
    returns a dict.  No side effects, no module-level state.
    """
    if env is None:
        env = os.environ

    postgres_host = env.get("POSTGRES_HOST", "postgres")
    postgres_port = env.get("POSTGRES_PORT", "5432")
    postgres_db = env.get("POSTGRES_DB", "postgres")
    postgres_user = env.get("POSTGRES_USER", "postgres")
    postgres_password = env.get("POSTGRES_PASSWORD", "postgres")
    postgres_collection_name = env.get("POSTGRES_COLLECTION_NAME", "memories")
    history_db_path = env.get("HISTORY_DB_PATH", "/app/history/history.db")

    openai_api_key = env.get("OPENAI_API_KEY")
    deepseek_api_key = env.get("DEEPSEEK_API_KEY")
    dashscope_api_key = env.get("DASHSCOPE_API_KEY")

    default_llm_model = env.get("MEM0_DEFAULT_LLM_MODEL", "gpt-4.1-nano-2025-04-14")
    default_embedder_model = env.get("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-3-small")
    default_embedding_dims = int(env.get("MEM0_DEFAULT_EMBEDDING_DIMS", "1536"))

    if deepseek_api_key and dashscope_api_key:
        llm_provider = "deepseek"
        llm_model = env.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
        llm_api_key = deepseek_api_key
        deepseek_base_url = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        embedder_provider = "openai"
        embedder_model = env.get("MEM0_DEFAULT_EMBEDDING_MODEL", "text-embedding-v4")
        embedder_api_key = dashscope_api_key
        embedder_base_url = env.get("DASHSCOPE_EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    else:
        llm_provider = "openai"
        llm_model = default_llm_model
        llm_api_key = openai_api_key
        embedder_provider = "openai"
        embedder_model = default_embedder_model
        embedder_api_key = openai_api_key

    llm_config: dict = {
        "api_key": llm_api_key,
        "temperature": 0.2,
        "model": llm_model,
    }
    if deepseek_api_key and dashscope_api_key:
        llm_config["deepseek_base_url"] = deepseek_base_url

    embedder_config: dict = {
        "api_key": embedder_api_key,
        "model": embedder_model,
        "embedding_dims": default_embedding_dims,
    }
    if deepseek_api_key and dashscope_api_key:
        embedder_config["openai_base_url"] = embedder_base_url

    return {
        "version": "v1.1",
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "host": postgres_host,
                "port": int(postgres_port),
                "dbname": postgres_db,
                "user": postgres_user,
                "password": postgres_password,
                "collection_name": postgres_collection_name,
                "embedding_model_dims": default_embedding_dims,
            },
        },
        "llm": {
            "provider": llm_provider,
            "config": llm_config,
        },
        "embedder": {
            "provider": embedder_provider,
            "config": embedder_config,
        },
        "history_db_path": history_db_path,
    }
