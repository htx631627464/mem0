"""Resolve Mem0 API endpoints for self-hosted agent plugins.

The self-hosted plugin must not silently fall back to a hosted service.
Operators need to set MEM0_API_HOST to the gateway base URL.
"""

from __future__ import annotations

import os

from _identity import resolve_api_base_url


def api_base_url() -> str:
    value = os.environ.get("MEM0_API_HOST", "").strip() or os.environ.get("MEM0_API_URL", "").strip()
    if not value:
        value = resolve_api_base_url()
    if not value:
        raise RuntimeError("MEM0_API_HOST is required for the self-hosted Mem0 plugin")
    return value.rstrip("/")


def api_url(path: str) -> str:
    return f"{api_base_url()}/{path.lstrip('/')}"
