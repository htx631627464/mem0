import json
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mem0_agent_gateway.app import create_app
from mem0_agent_gateway.config import GatewaySettings


AUTH_HEADERS = {"Authorization": "Token gateway-token"}
MCP_HEADERS = {
    **AUTH_HEADERS,
    "Accept": "application/json, text/event-stream",
}


class FakeMem0ServerClient:
    def __init__(self):
        self.calls = []
        self.memories = [
            {
                "id": "mem-1",
                "memory": "Keep gateway thin",
                "user_id": "nero",
                "agent_id": "mem0",
                "metadata": {"type": "decision", "app_id": "mem0"},
            },
            {
                "id": "mem-2",
                "memory": "Unrelated",
                "user_id": "nero",
                "agent_id": "other",
                "metadata": {"type": "task_learning", "app_id": "other"},
            },
        ]

    async def ping(self):
        self.calls.append(("ping", None))
        return {"status": "ok"}

    async def add_memory(self, payload):
        self.calls.append(("add_memory", payload))
        return {"results": [{"id": "mem-new", "memory": payload["messages"][0]["content"], "event": "ADD"}]}

    async def search_memories(self, payload):
        self.calls.append(("search_memories", payload))
        return {"results": [{"id": "mem-1", "memory": "Keep gateway thin", "score": 0.9}]}

    async def get_memories(self, params):
        self.calls.append(("get_memories", params))
        return {"results": list(self.memories)}

    async def get_memory(self, memory_id):
        self.calls.append(("get_memory", memory_id))
        return {"id": memory_id, "memory": "Current text", "metadata": {"type": "decision"}}

    async def update_memory(self, memory_id, payload):
        self.calls.append(("update_memory", {"memory_id": memory_id, "payload": payload}))
        return {"id": memory_id, "memory": payload["text"], "metadata": payload.get("metadata") or {}}

    async def delete_memory(self, memory_id):
        self.calls.append(("delete_memory", memory_id))
        return {"message": "Memory deleted successfully"}

    async def delete_all_memories(self, params):
        self.calls.append(("delete_all_memories", params))
        return {"message": "All relevant memories deleted"}

    async def list_entities(self):
        self.calls.append(("list_entities", None))
        return [{"id": "nero", "type": "user", "total_memories": 2}]

    async def delete_entity(self, entity_type, entity_id):
        self.calls.append(("delete_entity", {"entity_type": entity_type, "entity_id": entity_id}))
        return {"message": "Entity deleted"}


@pytest.fixture
def fake_client():
    return FakeMem0ServerClient()


@pytest.fixture
def app(fake_client):
    settings = GatewaySettings(
        gateway_token="gateway-token",
        mem0_server_url="http://mem0:8000",
        mem0_server_api_key="server-key",
    )
    return create_app(settings=settings, client=fake_client)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway") as ac:
        yield ac


def jsonrpc(method, params=None, req_id=1):
    payload = {"jsonrpc": "2.0", "method": method}
    if req_id is not None:
        payload["id"] = req_id
    if params is not None:
        payload["params"] = params
    return payload


@pytest.mark.asyncio
async def test_ping_requires_gateway_token(client):
    unauthenticated = await client.get("/v1/ping/")
    assert unauthenticated.status_code == 401

    invalid = await client.get("/v1/ping/", headers={"Authorization": "Token wrong"})
    assert invalid.status_code == 401

    valid = await client.get("/v1/ping/", headers=AUTH_HEADERS)
    assert valid.status_code == 200
    assert valid.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_add_memory_maps_app_id_to_agent_id_and_metadata(client, fake_client):
    response = await client.post(
        "/v3/memories/add/",
        headers=AUTH_HEADERS,
        json={
            "messages": [{"role": "user", "content": "Remember the gateway should stay thin"}],
            "user_id": "nero",
            "app_id": "mem0",
            "metadata": {"type": "decision"},
            "infer": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["event"] == "ADD"
    assert fake_client.calls[-1] == (
        "add_memory",
        {
            "messages": [{"role": "user", "content": "Remember the gateway should stay thin"}],
            "user_id": "nero",
            "agent_id": "mem0",
            "metadata": {"type": "decision", "app_id": "mem0"},
            "infer": False,
        },
    )


@pytest.mark.asyncio
async def test_search_memories_translates_app_id_and_metadata_filters(client, fake_client):
    response = await client.post(
        "/v3/memories/search/",
        headers=AUTH_HEADERS,
        json={
            "query": "gateway design",
            "filters": {
                "AND": [
                    {"user_id": "nero"},
                    {"app_id": "mem0"},
                    {"metadata": {"type": "decision"}},
                ]
            },
            "top_k": 3,
            "threshold": 0.2,
            "rerank": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == "mem-1"
    assert fake_client.calls[-1] == (
        "search_memories",
        {
            "query": "gateway design",
            "filters": {"user_id": "nero", "agent_id": "mem0", "type": "decision"},
            "top_k": 3,
            "threshold": 0.2,
        },
    )


@pytest.mark.asyncio
async def test_search_memories_maps_top_level_user_and_app_to_filters(client, fake_client):
    response = await client.post(
        "/v3/memories/search/",
        headers=AUTH_HEADERS,
        json={
            "query": "gateway design",
            "user_id": "nero",
            "app_id": "mem0",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == "mem-1"
    assert fake_client.calls[-1] == (
        "search_memories",
        {
            "query": "gateway design",
            "filters": {"user_id": "nero", "agent_id": "mem0"},
            "top_k": 5,
        },
    )


@pytest.mark.asyncio
async def test_search_memories_rejects_unscoped_requests_before_backend(client, fake_client):
    response = await client.post(
        "/v3/memories/search/",
        headers=AUTH_HEADERS,
        json={"query": "gateway design"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "search_memories requires a user_id, agent_id, app_id, or run_id scope"
    assert fake_client.calls == []


@pytest.mark.asyncio
async def test_get_memories_filters_and_paginates_compat_response(client, fake_client):
    response = await client.post(
        "/v3/memories/?page=1&page_size=1",
        headers=AUTH_HEADERS,
        json={
            "filters": {
                "AND": [
                    {"user_id": "nero"},
                    {"app_id": "mem0"},
                    {"metadata": {"type": "decision"}},
                ]
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["next"] is None
    assert body["previous"] is None
    assert body["results"] == [fake_client.memories[0]]
    assert fake_client.calls[-1] == ("get_memories", {"user_id": "nero", "agent_id": "mem0"})


@pytest.mark.asyncio
async def test_mcp_tools_list_exposes_mem0_compatible_names(client):
    init = await client.post("/mcp", headers=MCP_HEADERS, json=jsonrpc("initialize", req_id=1))
    assert init.status_code == 200

    response = await client.post("/mcp", headers=MCP_HEADERS, json=jsonrpc("tools/list", req_id=2))

    assert response.status_code == 200
    tool_names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {
        "add_memory",
        "search_memories",
        "get_memories",
        "get_memory",
        "update_memory",
        "delete_memory",
        "delete_all_memories",
        "delete_entities",
        "list_entities",
    }.issubset(tool_names)
    search_tool = next(tool for tool in response.json()["result"]["tools"] if tool["name"] == "search_memories")
    assert search_tool["inputSchema"]["required"] == ["query", "filters"]


@pytest.mark.asyncio
async def test_mcp_add_memory_calls_gateway_service(client, fake_client):
    await client.post("/mcp", headers=MCP_HEADERS, json=jsonrpc("initialize", req_id=1))

    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json=jsonrpc(
            "tools/call",
            {
                "name": "add_memory",
                "arguments": {
                    "text": "MCP should use the same gateway mapping",
                    "user_id": "nero",
                    "app_id": "mem0",
                    "metadata": {"type": "task_learning"},
                    "infer": False,
                },
            },
            req_id=2,
        ),
    )

    assert response.status_code == 200
    text = response.json()["result"]["content"][0]["text"]
    assert json.loads(text)["results"][0]["event"] == "ADD"
    assert fake_client.calls[-1][0] == "add_memory"
    assert fake_client.calls[-1][1]["agent_id"] == "mem0"
    assert fake_client.calls[-1][1]["metadata"]["app_id"] == "mem0"


@pytest.mark.asyncio
async def test_mcp_search_memories_reports_unscoped_request_without_backend_502(client, fake_client):
    await client.post("/mcp", headers=MCP_HEADERS, json=jsonrpc("initialize", req_id=1))

    response = await client.post(
        "/mcp",
        headers=MCP_HEADERS,
        json=jsonrpc(
            "tools/call",
            {
                "name": "search_memories",
                "arguments": {"query": "gateway design"},
            },
            req_id=2,
        ),
    )

    assert response.status_code == 200
    body = response.json()["result"]
    assert body["isError"] is True
    assert body["content"][0]["text"] == "search_memories requires a user_id, agent_id, app_id, or run_id scope"
    assert fake_client.calls == []
