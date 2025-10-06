from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, cast

import hmac
import jwt
from fastapi import HTTPException, status

from .config import SaraswatiSettings
from .elasticsearch_client import get_elasticsearch_client


async def login_native(username: str, password: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    client = get_elasticsearch_client(settings)
    index = settings.elasticsearch and settings.elasticsearch.users_index
    if not index:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Users index not configured")

    # Search for the user
    body = {"query": {"bool": {"should": [{"term": {"username.keyword": username}}, {"term": {"id.keyword": username}}], "minimum_should_match": 1}}}
    resp = await client.search(index=index, body=body, size=1)
    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = hits[0].get("_source") or {}

    stored_hash = user.get("password_hash")
    if not stored_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    candidate_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(candidate_hash, stored_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    username_norm = user.get("username") or user.get("id") or username
    normalized_user = {"id": user.get("id") or username_norm, "username": username_norm, "name": user.get("name") or username_norm, "roles": user.get("roles") or []}

    # Issue local JWT
    ttl = settings.auth_native.cache_ttl_seconds or 3600
    expires = int((datetime.now(timezone.utc) + timedelta(seconds=ttl)).timestamp())
    claims = {"sub": normalized_user["id"], "username": normalized_user["username"], "name": normalized_user["name"], "roles": normalized_user["roles"], "exp": expires, "aud": settings.auth_native.audience}
    token = jwt.encode(claims, settings.auth_native.jwt_secret, algorithm=settings.auth_native.jwt_algorithm)
    return {"access_token": cast(str, token), "user": normalized_user}


async def register_native(username: str, password: str, name: Optional[str], settings: SaraswatiSettings) -> Dict[str, Any]:
    index = settings.elasticsearch and settings.elasticsearch.users_index
    if not index:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Users index not configured")

    client = get_elasticsearch_client(settings)
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    doc = {"username": username, "name": name or username, "roles": ["author"], "password_hash": password_hash}
    resp = await client.index(index=index, document=doc)
    return {"ok": True, "id": resp.get("_id")}


async def introspect_native(token: str, settings: SaraswatiSettings) -> Dict[str, Any]:
    # Locally decode JWTs signed with jwt_secret
    try:
        payload = jwt.decode(token, settings.auth_native.jwt_secret, algorithms=[settings.auth_native.jwt_algorithm], audience=settings.auth_native.audience)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    payload.setdefault("active", True)
    return payload
