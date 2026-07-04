"""Tests for self-hosted API endpoint resolution."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def test_api_base_url_requires_explicit_env(monkeypatch, tmp_path):
    from _api import api_base_url

    monkeypatch.delenv("MEM0_API_HOST", raising=False)
    monkeypatch.delenv("MEM0_API_URL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="MEM0_API_HOST"):
        api_base_url()


def test_api_base_url_strips_trailing_slashes(monkeypatch):
    from _api import api_base_url

    monkeypatch.setenv("MEM0_API_HOST", "http://127.0.0.1:8765///")

    assert api_base_url() == "http://127.0.0.1:8765"


def test_api_url_joins_path(monkeypatch):
    from _api import api_url

    monkeypatch.setenv("MEM0_API_HOST", "https://memory.example.test/base/")

    assert api_url("/v3/memories/search/") == "https://memory.example.test/base/v3/memories/search/"
    assert api_url("v1/ping/") == "https://memory.example.test/base/v1/ping/"


def test_api_base_url_falls_back_to_shell_profile(monkeypatch, tmp_path):
    from _api import api_base_url

    monkeypatch.delenv("MEM0_API_HOST", raising=False)
    monkeypatch.delenv("MEM0_API_URL", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (tmp_path / ".zshrc").write_text('export MEM0_API_HOST="http://127.0.0.1:8765"\n', encoding="utf-8")

    assert api_base_url() == "http://127.0.0.1:8765"


def test_identity_shell_exports_endpoint_vars_from_profile(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "_identity.sh"
    (tmp_path / ".zshrc").write_text(
        "\n".join(
            [
                'export MEM0_API_KEY="test-token"',
                'export MEM0_API_HOST="http://127.0.0.1:8765"',
                'export MEM0_API_URL="http://127.0.0.1:8765"',
                'export MEM0_MCP_URL="http://127.0.0.1:8765/mcp"',
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            "-lc",
            (
                f'source "{script}"; '
                'printf "%s\\n%s\\n%s\\n" "$MEM0_API_HOST" "$MEM0_API_URL" "$MEM0_MCP_URL"'
            ),
        ],
        cwd=tmp_path,
        env={"HOME": str(tmp_path), "USER": "tester", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        "http://127.0.0.1:8765",
        "http://127.0.0.1:8765",
        "http://127.0.0.1:8765/mcp",
    ]
