"""Tests that the OpenCode plugin has no cloud fallback in self-hosted mode."""

from __future__ import annotations

import json
import re
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
OPENCODE_ROOT = PLUGIN_ROOT / ".opencode-plugin"


def test_opencode_mcp_uses_env_url():
    data = json.loads((OPENCODE_ROOT / "opencode.json").read_text())

    server = data["mcp"]["mem0"]
    assert server["type"] == "remote"
    assert server["url"] == "{env:MEM0_MCP_URL}"
    assert server["headers"]["Authorization"] == "Token {env:MEM0_API_KEY}"
    assert server["oauth"] is False


def test_opencode_runtime_files_have_no_cloud_mem0_hosts():
    runtime_files = [
        OPENCODE_ROOT / "opencode.json",
        OPENCODE_ROOT / "cli.ts",
        OPENCODE_ROOT / "opencode-mem0.ts",
    ]
    offenders: list[str] = []
    for path in runtime_files:
        text = path.read_text(encoding="utf-8")
        if "api.mem0.ai" in text or "mcp.mem0.ai" in text or "app.mem0.ai" in text:
            offenders.append(str(path.relative_to(PLUGIN_ROOT)))

    assert offenders == []


def test_opencode_hooks_require_explicit_api_host():
    source = (OPENCODE_ROOT / "opencode-mem0.ts").read_text(encoding="utf-8")

    assert "MEM0_API_HOST" in source
    assert "MEM0_API_URL" in source
    assert "new MemoryClient({ apiKey })" not in source
    assert re.search(r"new MemoryClient\(\{\s*apiKey,\s*host: apiHost,?\s*\}\)", source)
