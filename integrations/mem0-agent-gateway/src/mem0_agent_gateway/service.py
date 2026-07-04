from __future__ import annotations

from math import ceil
from typing import Any, Protocol

from .filters import extract_entities, memory_matches_filter, normalize_filters


class Mem0Backend(Protocol):
    async def ping(self) -> dict[str, Any]: ...
    async def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def search_memories(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def get_memories(self, params: dict[str, Any]) -> dict[str, Any]: ...
    async def get_memory(self, memory_id: str) -> dict[str, Any]: ...
    async def update_memory(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def delete_memory(self, memory_id: str) -> dict[str, Any]: ...
    async def delete_all_memories(self, params: dict[str, Any]) -> dict[str, Any]: ...
    async def list_entities(self) -> list[dict[str, Any]]: ...
    async def delete_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]: ...


SEARCH_SCOPE_ERROR = "search_memories requires a user_id, agent_id, app_id, or run_id scope"


class GatewayService:
    def __init__(self, backend: Mem0Backend):
        self._backend = backend

    async def ping(self) -> dict[str, Any]:
        await self._backend.ping()
        return {
            "status": "ok",
            "message": "self-hosted mem0 gateway is reachable",
            "org_id": None,
            "project_id": None,
            "user_email": None,
        }

    async def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._backend.add_memory(self._normalize_add_payload(payload))

    async def search_memories(self, payload: dict[str, Any]) -> dict[str, Any]:
        request: dict[str, Any] = {"query": payload.get("query", "")}
        filters = _search_filters_for_server(normalize_filters(payload.get("filters")), payload)
        if not extract_entities(filters):
            raise ValueError(SEARCH_SCOPE_ERROR)
        if filters:
            request["filters"] = filters
        top_k = payload.get("top_k", payload.get("topK", payload.get("limit")))
        if top_k is not None:
            request["top_k"] = top_k
        if payload.get("threshold") is not None:
            request["threshold"] = payload["threshold"]
        if payload.get("explain") is not None:
            request["explain"] = payload["explain"]
        return await self._backend.search_memories(request)

    async def get_memories(self, payload: dict[str, Any], page: int = 1, page_size: int = 100) -> dict[str, Any]:
        filters = normalize_filters(payload.get("filters"))
        params = extract_entities(filters)
        response = await self._backend.get_memories(params)
        memories = _as_results(response)
        if filters:
            memories = [memory for memory in memories if memory_matches_filter(memory, filters)]
        return _paginate(memories, page=page, page_size=page_size)

    async def get_memory(self, memory_id: str) -> dict[str, Any]:
        return await self._backend.get_memory(memory_id)

    async def update_memory(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        if "text" not in body:
            existing = await self._backend.get_memory(memory_id)
            existing_text = existing.get("memory") or existing.get("text") or existing.get("data")
            body["text"] = existing_text or ""
        body = {key: value for key, value in body.items() if key in {"text", "metadata"} and value is not None}
        return await self._backend.update_memory(memory_id, body)

    async def delete_memory(self, memory_id: str) -> dict[str, Any]:
        return await self._backend.delete_memory(memory_id)

    async def delete_all_memories(self, payload: dict[str, Any]) -> dict[str, Any]:
        filters = payload.get("filters")
        params = extract_entities(filters)
        for source, target in (("user_id", "user_id"), ("agent_id", "agent_id"), ("run_id", "run_id")):
            if payload.get(source) and target not in params:
                params[target] = payload[source]
        if payload.get("app_id") and "agent_id" not in params:
            params["agent_id"] = payload["app_id"]
        return await self._backend.delete_all_memories(params)

    async def list_entities(self) -> list[dict[str, Any]]:
        return await self._backend.list_entities()

    async def delete_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        backend_type = "agent" if entity_type == "app" else entity_type
        return await self._backend.delete_entity(backend_type, entity_id)

    def _normalize_add_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        filters = normalize_filters(body.pop("filters", None))
        entities = extract_entities(filters)

        app_id = body.pop("app_id", body.pop("appId", None))
        metadata = dict(body.get("metadata") or {})
        if app_id:
            metadata.setdefault("app_id", app_id)
            body.setdefault("agent_id", app_id)

        for key, value in entities.items():
            body.setdefault(key, value)

        if body.get("text") and not body.get("messages"):
            body["messages"] = [{"role": "user", "content": body.pop("text")}]
        if body.get("memory") and not body.get("messages"):
            body["messages"] = [{"role": "user", "content": body.pop("memory")}]

        allowed = {"messages", "user_id", "agent_id", "run_id", "infer", "memory_type", "prompt"}
        normalized = {key: value for key, value in body.items() if key in allowed and value is not None}
        if metadata:
            normalized["metadata"] = metadata
        return normalized


def _as_results(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []
    results = response.get("results", response.get("memories", []))
    return results if isinstance(results, list) else []


def _search_filters_for_server(filters: Any, payload: dict[str, Any]) -> Any:
    flat_filters: dict[str, Any] = {}

    def collect(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                collect(item)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key == "AND":
                collect(value)
            elif key in {"OR", "NOT"}:
                continue
            else:
                flat_filters.setdefault(key, value)

    collect(filters)

    for source, target in (("user_id", "user_id"), ("agent_id", "agent_id"), ("run_id", "run_id")):
        if payload.get(source):
            flat_filters.setdefault(target, payload[source])
    if payload.get("app_id") and not payload.get("agent_id"):
        flat_filters.setdefault("agent_id", payload["app_id"])
    if payload.get("appId") and not payload.get("agent_id"):
        flat_filters.setdefault("agent_id", payload["appId"])

    return flat_filters or filters


def _paginate(memories: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(page_size, 1)
    start = (page - 1) * page_size
    end = start + page_size
    total = len(memories)
    pages = ceil(total / page_size) if total else 1
    return {
        "count": total,
        "next": page + 1 if page < pages else None,
        "previous": page - 1 if page > 1 and page <= pages + 1 else None,
        "results": memories[start:end],
    }
