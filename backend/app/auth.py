from __future__ import annotations

from typing import Any, Dict

import base64

from fastapi import Depends, HTTPException, Request, status
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
    request: Request = None,
) -> Dict[str, Any]:
    if credentials is None:
        # allow HTTP Basic as a convenience for clients that can send credentials
        # directly. The backend will exchange credentials with the configured
        # login flow and then introspect the returned token to obtain claims.
        auth_header = None
        if request is not None:
            auth_header = request.headers.get("authorization")

        if auth_header and auth_header.lower().startswith("basic "):
            try:
                b64 = auth_header.split(None, 1)[1]
                decoded = base64.b64decode(b64).decode("utf-8")
                username, password = decoded.split(":", 1)
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Basic auth header")

            # Use existing login flow (which will proxy to external provider or
            # perform native login depending on `auth_system`). Expect a dict
            # containing an `access_token` on success.
            try:
                login_resp = await login(username, password, settings)
            except HTTPException as exc:
                # preserve 401/403 semantics
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from exc

            token = login_resp.get("access_token")
            if not token:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login did not return a token")

            claims = await introspect_token(token, settings)
            return claims

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    token = credentials.credentials
    claims = await introspect_token(token, settings)
    return claims
