from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from .auth import require_gateway_auth
from .client import Mem0ServerClient
from .config import GatewaySettings
from .mcp import handle_jsonrpc
from .service import GatewayService, Mem0Backend


def create_app(settings: GatewaySettings, client: Mem0Backend | None = None) -> FastAPI:
    backend = client or Mem0ServerClient(settings)
    service = GatewayService(backend)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            close = getattr(backend, "close", None)
            if close is not None:
                await close()

    app = FastAPI(
        title="Mem0 Agent Gateway",
        version="0.1.0",
        redirect_slashes=False,
        lifespan=lifespan,
    )

    async def auth_dependency(request: Request) -> None:
        require_gateway_auth(request, settings)

    @app.exception_handler(httpx.HTTPStatusError)
    async def http_status_error_handler(_request: Request, exc: httpx.HTTPStatusError):
        try:
            detail: Any = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return JSONResponse(status_code=exc.response.status_code, content={"detail": detail})

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/ping/", dependencies=[Depends(auth_dependency)])
    async def ping() -> dict[str, Any]:
        return await service.ping()

    @app.post("/v3/memories/add/", dependencies=[Depends(auth_dependency)])
    async def add_memory(payload: dict[str, Any]) -> dict[str, Any]:
        return await service.add_memory(payload)

    @app.post("/v3/memories/search/", dependencies=[Depends(auth_dependency)])
    async def search_memories(payload: dict[str, Any]) -> dict[str, Any]:
        return await service.search_memories(payload)

    @app.post("/v3/memories/", dependencies=[Depends(auth_dependency)])
    async def get_memories(
        payload: dict[str, Any],
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1),
    ) -> dict[str, Any]:
        return await service.get_memories(payload, page=page, page_size=page_size)

    @app.get("/v1/memories/{memory_id}/", dependencies=[Depends(auth_dependency)])
    async def get_memory(memory_id: str) -> dict[str, Any]:
        return await service.get_memory(memory_id)

    @app.put("/v1/memories/{memory_id}/", dependencies=[Depends(auth_dependency)])
    async def update_memory(memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await service.update_memory(memory_id, payload)

    @app.delete("/v1/memories/{memory_id}/", dependencies=[Depends(auth_dependency)])
    async def delete_memory(memory_id: str) -> dict[str, Any]:
        return await service.delete_memory(memory_id)

    @app.delete("/v1/memories/", dependencies=[Depends(auth_dependency)])
    async def delete_all_memories(request: Request) -> dict[str, Any]:
        return await service.delete_all_memories(dict(request.query_params))

    @app.get("/v1/entities/", dependencies=[Depends(auth_dependency)])
    async def list_entities() -> list[dict[str, Any]]:
        return await service.list_entities()

    @app.delete("/v1/entities/{entity_type}/{entity_id}/", dependencies=[Depends(auth_dependency)])
    @app.delete("/v2/entities/{entity_type}/{entity_id}/", dependencies=[Depends(auth_dependency)])
    async def delete_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
        return await service.delete_entity(entity_type, entity_id)

    @app.post("/mcp", dependencies=[Depends(auth_dependency)])
    @app.post("/mcp/", dependencies=[Depends(auth_dependency)])
    async def mcp_endpoint(request: Request) -> Response:
        accept = request.headers.get("accept", "")
        if "application/json" not in accept and "*/*" not in accept:
            return JSONResponse(status_code=406, content={"detail": "Accept header must include application/json"})
        payload = await request.json()
        response = await handle_jsonrpc(service, payload)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(content=response)

    return app


def create_app_from_env() -> FastAPI:
    return create_app(GatewaySettings.from_env())
