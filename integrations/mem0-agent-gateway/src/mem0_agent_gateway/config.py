from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewaySettings:
    gateway_token: str
    mem0_server_url: str
    mem0_server_api_key: str
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            gateway_token=_required_env("MEM0_GATEWAY_TOKEN"),
            mem0_server_url=_required_env("MEM0_SERVER_URL").rstrip("/"),
            mem0_server_api_key=_required_env("MEM0_SERVER_API_KEY"),
            request_timeout_seconds=float(os.environ.get("MEM0_GATEWAY_TIMEOUT_SECONDS", "30")),
        )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
