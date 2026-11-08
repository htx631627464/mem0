from __future__ import annotations

import json
from typing import Any

from .service import GatewayService

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "mem0-agent-gateway", "version": "0.1.0"}


async def handle_jsonrpc(service: GatewayService, payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list):
        responses = [await handle_jsonrpc(service, item) for item in payload]
        return [item for item in responses if item is not None]  # type: ignore[return-value]
    if not isinstance(payload, dict):
        return _error(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _result(request_id, {"tools": tools_list()})
    if method == "tools/call":
        return await _handle_tool_call(service, request_id, params)

    return _error(request_id, -32601, f"Method not found: {method}")


def tools_list() -> list[dict[str, Any]]:
    return [
        _tool(
            "add_memory",
            "Save text or conversation history for a user, agent, app, or run.",
            {
                "text": {"type": "string"},
                "messages": {"type": "array", "items": {"type": "object"}},
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "metadata": {"type": "object"},
                "infer": {"type": "boolean"},
            },
        ),
        _tool(
            "search_memories",
            "Semantic search across stored memories.",
            {
                "query": {"type": "string"},
                "filters": {"type": "object"},
                "top_k": {"type": "integer"},
                "threshold": {"type": "number"},
            },
            required=["query", "filters"],
        ),
        _tool(
            "get_memories",
            "List memories with filters and pagination.",
            {
                "filters": {"type": "object"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            },
        ),
        _tool(
            "get_memory",
            "Retrieve a specific memory by ID.",
            {"memory_id": {"type": "string"}},
            required=["memory_id"],
        ),
        _tool(
            "update_memory",
            "Overwrite a memory text and optional metadata by ID.",
            {
                "memory_id": {"type": "string"},
                "text": {"type": "string"},
                "metadata": {"type": "object"},
                "source": {"type": "string"},
            },
            required=["memory_id"],
        ),
        _tool(
            "delete_memory",
            "Delete a single memory by ID.",
            {"memory_id": {"type": "string"}},
            required=["memory_id"],
        ),
        _tool(
            "delete_all_memories",
            "Delete memories in a user, agent, app, or run scope.",
            {
                "filters": {"type": "object"},
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
        ),
        _tool(
            "delete_entities",
            "Delete one entity and its memories.",
            {
                "entity_type": {"type": "string", "enum": ["user", "agent", "app", "run"]},
                "entity_id": {"type": "string"},
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
        ),
        _tool("list_entities", "List users, agents/apps, and runs.", {}),
    ]


async def _handle_tool_call(service: GatewayService, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _tool_error(request_id, "Tool arguments must be an object")

    try:
        if name == "add_memory":
            result = await service.add_memory(arguments)
        elif name == "search_memories":
            result = await service.search_memories(arguments)
        elif name == "get_memories":
            result = await service.get_memories(
                arguments,
                page=int(arguments.get("page", 1)),
                page_size=int(arguments.get("page_size", arguments.get("pageSize", 100))),
            )
        elif name == "get_memory":
            result = await service.get_memory(_required(arguments, "memory_id"))
        elif name == "update_memory":
            memory_id = _required(arguments, "memory_id")
            metadata = dict(arguments.get("metadata") or {})
            if arguments.get("source"):
                metadata.setdefault("source", arguments["source"])
            result = await service.update_memory(memory_id, {"text": arguments.get("text"), "metadata": metadata})
        elif name == "delete_memory":
            result = await service.delete_memory(_required(arguments, "memory_id"))
        elif name == "delete_all_memories":
            result = await service.delete_all_memories(arguments)
        elif name == "list_entities":
            result = await service.list_entities()
        elif name == "delete_entities":
            result = await _delete_entities(service, arguments)
        else:
            return _tool_error(request_id, f"Unknown tool: {name}")
    except Exception as exc:
        return _tool_error(request_id, str(exc))

    return _result(request_id, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]})


async def _delete_entities(service: GatewayService, arguments: dict[str, Any]) -> Any:
    if arguments.get("entity_type") and arguments.get("entity_id"):
        return await service.delete_entity(arguments["entity_type"], arguments["entity_id"])

    requested = [
        ("user", arguments.get("user_id")),
        ("agent", arguments.get("agent_id")),
        ("app", arguments.get("app_id")),
        ("run", arguments.get("run_id")),
    ]
    entities = [(entity_type, entity_id) for entity_type, entity_id in requested if entity_id]
    if not entities:
        raise ValueError("At least one entity identifier is required")

    results = []
    for entity_type, entity_id in entities:
        results.append(await service.delete_entity(entity_type, entity_id))
    return {"results": results}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


def _required(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not value:
        raise ValueError(f"{key} is required")
    return str(value)


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_error(request_id: Any, message: str) -> dict[str, Any]:
    return _result(request_id, {"content": [{"type": "text", "text": message}], "isError": True})
