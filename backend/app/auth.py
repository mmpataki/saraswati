from __future__ import annotations

from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import SaraswatiSettings, get_settings
from .auth_external import login_external, introspect_external
from .auth_native import login_native, register_native, introspect_native

_security = HTTPBearer(auto_error=False)


async def login(username: str, password: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    mode = settings.auth_system
    if mode == "elastic":
        return await login_native(username, password, settings)
    if mode == "introspect":
        return await login_external(username, password, settings)
    if mode == "decode":
        # decode mode doesn't support server-side login; default to native for local users
        return await login_native(username, password, settings)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported auth mode")


async def register(username: str, password: str, name: str | None, settings: SaraswatiSettings) -> Dict[str, Any]:
    mode = settings.auth_system
    if mode in ("elastic", "decode"):
        return await register_native(username, password, name, settings)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration disabled")


async def introspect_token(token: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    mode = settings.auth_system
    if mode == "elastic" or mode == "decode":
        return await introspect_native(token, settings)
    if mode == "introspect":
        return await introspect_external(token, settings)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unsupported auth mode")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    settings: SaraswatiSettings = Depends(get_settings),
) -> Dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    token = credentials.credentials
    claims = await introspect_token(token, settings)
    return claims
