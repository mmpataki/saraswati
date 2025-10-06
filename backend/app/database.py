from __future__ import annotations

from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient

from .config import SaraswatiSettings, get_settings


@lru_cache(maxsize=1)
def get_mongo_client(settings: SaraswatiSettings | None = None) -> AsyncIOMotorClient:
    cfg = settings or get_settings()
    if not cfg.mongo:
        raise ValueError("Mongo configuration is missing")
    return AsyncIOMotorClient(cfg.mongo.uri)
