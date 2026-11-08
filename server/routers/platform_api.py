"""mem0 Platform API compatibility layer (/v1, /v3).

Official mem0 clients (the mem0ai TS SDK, e.g. behind
``@mem0/pi-agent-plugin``) speak the hosted Platform API:
``Authorization: Token <key>`` auth plus ``/v1``/``/v3`` endpoints with
``app_id`` scoping. This router translates that surface onto the native
self-hosted handlers so those clients run against this server unchanged.

``app_id`` handling mirrors the agent-gateway recipe: the value is stored
both as payload metadata and as the ``agent_id`` alias so scoped search and
entity listing keep working on the native API.
"""

import secrets
from typing import Any, Dict, List, Optional

from auth import (
    ADMIN_API_KEY,
    AUTH_DISABLED,
    _mark_auth_type,
    _resolve_user_from_api_key,
)
from db import SessionLocal
from errors import upstream_error
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from models import User
from pydantic import BaseModel, Field
from memory_policy import drop_user_narration
from server_state import get_memory_instance

router = APIRouter(tags=["platform-api"])


async def verify_platform_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[User]:
    """Authenticate platform clients via ``Authorization: Token <key>``.

    Accepts the SDK's ``Token`` scheme (and ``Bearer``/``X-API-Key`` as a
    courtesy) and validates against the same api_keys/ADMIN_API_KEY store
    as the native API.
    """
    token: Optional[str] = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() in {"token", "bearer"} and value:
            token = value.strip()
    if token is None and x_api_key is not None:
        token = x_api_key

    if token is None:
        if AUTH_DISABLED:
            _mark_auth_type(request, "disabled")
            return None
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide 'Authorization: Token <key>'.",
        )

    if ADMIN_API_KEY and secrets.compare_digest(token, ADMIN_API_KEY):
        _mark_auth_type(request, "admin_api_key")
        return None

    user = None
    with SessionLocal() as db:
        user = _resolve_user_from_api_key(token, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    _mark_auth_type(request, "api_key")
    return user


class PlatformMessage(BaseModel):
    role: str = Field(..., description="Role of the message (user or assistant).")
    content: str = Field(..., description="Message content.")


class PlatformAddRequest(BaseModel):
    messages: List[PlatformMessage] = Field(..., description="List of messages to store.")
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    app_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    infer: Optional[bool] = None


class PlatformSearchRequest(BaseModel):
    query: str = Field(..., description="Search query.")
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    threshold: Optional[float] = None


class PlatformListRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None


class PlatformUpdateRequest(BaseModel):
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/v1/ping/")
def platform_ping(_auth=Depends(verify_platform_auth)):
    """SDK health probe."""
    return {"status": "ok", "service": "self-hosted mem0 platform-api"}


@router.post("/v3/memories/add/")
def platform_add(body: PlatformAddRequest, _auth=Depends(verify_platform_auth)):
    """SDK add(): messages plus entity scopes, app_id folded into metadata/agent_id."""
    if not any([body.user_id, body.agent_id, body.run_id, body.app_id]):
        raise HTTPException(
            status_code=400,
            detail="At least one identifier (user_id, agent_id, app_id, run_id) is required.",
        )

    params: Dict[str, Any] = {}
    if body.user_id is not None:
        params["user_id"] = body.user_id
    if body.run_id is not None:
        params["run_id"] = body.run_id
    metadata = dict(body.metadata or {})
    if body.app_id:
        metadata.setdefault("app_id", body.app_id)
        params.setdefault("agent_id", body.agent_id or body.app_id)
    elif body.agent_id:
        params["agent_id"] = body.agent_id
    if metadata:
        params["metadata"] = metadata
    if body.infer is not None:
        params["infer"] = body.infer

    try:
        memory = get_memory_instance()
        response = memory.add(
            messages=[m.model_dump() for m in body.messages], **params
        )
        return drop_user_narration(memory, response)
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/search/")
def platform_search(body: PlatformSearchRequest, _auth=Depends(verify_platform_auth)):
    """SDK search(): filters pass straight through (pgvector filters any payload key)."""
    params: Dict[str, Any] = {}
    if body.filters:
        params["filters"] = body.filters
    if body.top_k is not None:
        params["top_k"] = body.top_k
    if body.threshold is not None:
        params["threshold"] = body.threshold
    try:
        return get_memory_instance().search(query=body.query, **params)
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/")
def platform_list(
    body: PlatformListRequest,
    page: int = 1,
    page_size: int = 100,
    _auth=Depends(verify_platform_auth),
):
    """SDK getAll(): POST /v3/memories/ with body filters, page params in query.

    The underlying get_all defaults to top_k=20, which would silently hide
    memories from platform clients — fetch wide here and paginate in memory.
    """
    try:
        response = get_memory_instance().get_all(filters=body.filters or {}, top_k=1000)
        results = response.get("results", []) if isinstance(response, dict) else list(response)
        start = (page - 1) * page_size
        return {"results": results[start : start + page_size], "count": len(results)}
    except Exception:
        raise upstream_error()


@router.put("/v1/memories/{memory_id}/")
def platform_update(memory_id: str, body: PlatformUpdateRequest, _auth=Depends(verify_platform_auth)):
    """SDK update(): overwrite text/metadata by id."""
    if body.text is None and body.metadata is None:
        raise HTTPException(status_code=400, detail="text or metadata is required.")
    try:
        return get_memory_instance().update(
            memory_id=memory_id, data=body.text, metadata=body.metadata
        )
    except Exception:
        raise upstream_error()


@router.delete("/v1/memories/{memory_id}/")
def platform_delete(memory_id: str, _auth=Depends(verify_platform_auth)):
    """SDK delete(): remove one memory by id."""
    try:
        get_memory_instance().delete(memory_id=memory_id)
        return {"message": "Memory deleted successfully"}
    except Exception:
        raise upstream_error()


@router.delete("/v1/memories/")
def platform_delete_all(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    app_id: Optional[str] = None,
    _auth=Depends(verify_platform_auth),
):
    """SDK deleteAll().

    ``app_id`` scopes are not native to the underlying delete_all, so they
    are resolved to ids first and deleted one by one — a project-scoped
    delete must never widen to the whole user. Unscoped deletes require the
    ADMIN key.
    """
    if not any([user_id, agent_id, run_id, app_id]):
        raise HTTPException(
            status_code=400,
            detail="At least one identifier (user_id, agent_id, app_id, run_id) is required.",
        )

    if app_id is None:
        if _auth is not None:
            raise HTTPException(
                status_code=403,
                detail="Unscoped delete-all requires the ADMIN API key.",
            )
        params = {
            k: v
            for k, v in {"user_id": user_id, "agent_id": agent_id, "run_id": run_id}.items()
            if v is not None
        }
        try:
            get_memory_instance().delete_all(**params)
            return {"message": "All relevant memories deleted"}
        except Exception:
            raise upstream_error()

    filters = {
        k: v
        for k, v in {
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "app_id": app_id,
        }.items()
        if v is not None
    }
    try:
        response = get_memory_instance().get_all(filters=filters)
        results = response.get("results", []) if isinstance(response, dict) else list(response)
        for row in results:
            get_memory_instance().delete(memory_id=row["id"])
        return {"message": f"Deleted {len(results)} memories", "count": len(results)}
    except Exception:
        raise upstream_error()
