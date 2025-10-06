from __future__ import annotations

from typing import Any, Dict

import time
import threading

import httpx
from fastapi import HTTPException, status

from .config import SaraswatiSettings


# Simple in-memory cache (module-level so it's shared across calls in the same process).
# Maps token -> (expiry_timestamp, data)
_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()


async def login_external(username: str, password: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    """Proxy login to an external auth service and normalize the response."""
    if not settings.auth_external.service:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="External auth service not configured")

    async with httpx.AsyncClient(base_url=str(settings.auth_external.service), timeout=10) as client:
        response = await client.post(settings.auth_external.login_path, json={"username": username, "password": password})

    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    data = response.json()
    token = data.get("access_token") or data.get("token")
    auth_ok = data.get("auth", True)
    if not token or not auth_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_info: Dict[str, Any] = data.get("user") or {}
    username_norm = user_info.get("username") or user_info.get("id") or username
    normalized_user = {
        "id": user_info.get("id") or username_norm,
        "username": username_norm,
        "name": user_info.get("name") or username_norm,
        "roles": user_info.get("roles") or user_info.get("role") or [],
    }

    return {"access_token": token, "user": normalized_user}


async def introspect_external(token: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    if not settings.auth_external.service:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="External auth service not configured")

    # Simple in-memory TTL cache keyed by token. We only cache successful/active responses.
    # Cache is process-local (no persistence) and protected by a lock for thread-safety.
    path = settings.auth_external.introspect_path or "/introspect"
    cache_ttl = int(settings.auth_external.cache_ttl_seconds or 0)

    # Check cache first
    with _cache_lock:
        entry = _cache.get(token)
        if entry:
            expiry, cached = entry
            if expiry > time.time():
                return cached
            else:
                # expired
                del _cache[token]

    async with httpx.AsyncClient(base_url=str(settings.auth_external.service), timeout=10) as client:
        response = await client.post(path, json={"token": token, "audience": settings.auth_external.audience})

    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    data = response.json()
    active = data.get("active")
    if active is None:
        active = bool(data.get("auth"))
        data["active"] = active
    if not active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inactive")

    # Cache positive/introspected responses if TTL configured
    if cache_ttl and data.get("active"):
        expiry_ts = time.time() + cache_ttl
        with _cache_lock:
            _cache[token] = (expiry_ts, data)
    return data
