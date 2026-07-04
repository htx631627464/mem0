from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("MEM0_GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("MEM0_GATEWAY_PORT", "8765"))
    uvicorn.run("mem0_agent_gateway.app:create_app_from_env", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
