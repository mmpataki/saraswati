from __future__ import annotations

from typing import Any, Dict

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..config import SaraswatiSettings, get_settings
# import auth facade functions with aliases to avoid shadowing the route handler names
from ..auth import login as auth_login, register as auth_register

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(payload: LoginRequest, settings: SaraswatiSettings = Depends(get_settings)) -> Dict[str, Any]:
    return await auth_login(payload.username, payload.password, settings)


@router.get("/capabilities")
async def capabilities(settings: SaraswatiSettings = Depends(get_settings)) -> Dict[str, Any]:
    """Expose authentication capabilities to the frontend.

    - registration is allowed only when the backend is using Elasticsearch-backed auth (elastic)
      or local decode mode. When using a remote external auth (`introspect`) registration is
      disabled because the external provider is the source of truth for users.
    """
    mode = settings.auth_system
    can_register = mode in ("elastic", "decode")
    return {"can_register": can_register, "auth_system": mode}


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str | None = None


@router.post("/register")
async def register(payload: RegisterRequest, settings: SaraswatiSettings = Depends(get_settings)) -> Dict[str, Any]:
    """Register a new user in Elasticsearch when backend allows registration.

    This endpoint is intentionally minimal: it computes a SHA256 hex digest of the password
    and stores it in `password_hash`. For production, replace this with a proper
    password hashing algorithm (bcrypt/argon2) and admin approval flow.
    """
    return await auth_register(payload.username.strip(), payload.password, payload.name, settings)
