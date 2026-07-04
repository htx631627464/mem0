from __future__ import annotations

from typing import Any

import httpx

from .config import GatewaySettings


class Mem0ServerClient:
    def __init__(self, settings: GatewaySettings):
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.mem0_server_url.rstrip("/"),
            timeout=settings.request_timeout_seconds,
            headers={"X-API-Key": settings.mem0_server_api_key},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> dict[str, Any]:
        response = await self._client.get("/configure")
        response.raise_for_status()
        return {"status": "ok"}

    async def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/memories", json=payload)
        response.raise_for_status()
        return response.json()

    async def search_memories(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post("/search", json=payload)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"results": data}

    async def get_memories(self, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get("/memories", params=params)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"results": data}

    async def get_memory(self, memory_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/memories/{memory_id}")
        response.raise_for_status()
        return response.json()

    async def update_memory(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.put(f"/memories/{memory_id}", json=payload)
        response.raise_for_status()
        return response.json()

    async def delete_memory(self, memory_id: str) -> dict[str, Any]:
        response = await self._client.delete(f"/memories/{memory_id}")
        response.raise_for_status()
        return response.json()

    async def delete_all_memories(self, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.delete("/memories", params=params)
        response.raise_for_status()
        return response.json()

    async def list_entities(self) -> list[dict[str, Any]]:
        response = await self._client.get("/entities")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else data.get("results", [])

    async def delete_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        response = await self._client.delete(f"/entities/{entity_type}/{entity_id}")
        response.raise_for_status()
        return response.json()
