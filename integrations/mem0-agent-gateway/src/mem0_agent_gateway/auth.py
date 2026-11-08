from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from .config import GatewaySettings


def require_gateway_auth(request: Request, settings: GatewaySettings) -> None:
    token = _extract_token(request)
    if token and secrets.compare_digest(token, settings.gateway_token):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(request: Request) -> str:
    x_api_key = request.headers.get("X-API-Key", "").strip()
    if x_api_key:
        return x_api_key

    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        return ""

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() in {"bearer", "token"} and value.strip():
        return value.strip()
    return ""
