"""Tests that the Codex plugin has no cloud fallback in self-hosted mode."""

from __future__ import annotations

import json
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_codex_plugin_manifest_uses_standard_mcp_manifest():
    data = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())

    assert data["mcpServers"] == "./.mcp.json"
    assert data["hooks"] == "./hooks/codex-hooks.json"


def test_codex_mcp_uses_self_hosted_http_server():
    data = json.loads((PLUGIN_ROOT / ".mcp.json").read_text())

    server = data["mcpServers"]["mem0"]
    assert server["type"] == "http"
    assert server["url"] == "http://127.0.0.1:8765/mcp"
    assert server["bearer_token_env_var"] == "MEM0_API_KEY"
    assert "headers" not in server


def test_codex_runtime_files_have_no_cloud_mem0_hosts():
    runtime_files = [
        PLUGIN_ROOT / ".mcp.json",
        PLUGIN_ROOT / "mcp_config.json",
        *sorted((PLUGIN_ROOT / "scripts").glob("*.py")),
        *sorted((PLUGIN_ROOT / "scripts").glob("*.sh")),
    ]
    offenders: list[str] = []
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        if "api.mem0.ai" in text or "mcp.mem0.ai" in text or "app.mem0.ai" in text:
            offenders.append(str(path.relative_to(PLUGIN_ROOT)))

    assert offenders == []


def test_codex_category_setup_uses_explicit_api_host():
    auto_setup = (PLUGIN_ROOT / "scripts" / "auto_setup_categories.py").read_text(encoding="utf-8")
    setup = (PLUGIN_ROOT / "scripts" / "setup_coding_categories.py").read_text(encoding="utf-8")

    assert "api_base_url" in auto_setup
    assert "MemoryClient(host=api_base_url())" in auto_setup
    assert "api_base_url" in setup
    assert "MemoryClient(host=api_host)" in setup
    assert "MemoryClient()" not in auto_setup
    assert "MemoryClient()" not in setup


def test_codex_search_hooks_allow_two_slow_searches():
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "codex-hooks.json").read_text(encoding="utf-8"))["hooks"]

    user_prompt_timeout = hooks["UserPromptSubmit"][0]["hooks"][0]["timeout"]
    bash_timeout = hooks["PostToolUse"][1]["hooks"][0]["timeout"]

    assert user_prompt_timeout >= 35
    assert bash_timeout >= 35
