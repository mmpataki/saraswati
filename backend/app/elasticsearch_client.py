from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Tuple

from elasticsearch import AsyncElasticsearch

from .config import SaraswatiSettings, get_settings


def _build_client_kwargs_from_settings(settings: SaraswatiSettings) -> Dict[str, Any]:
    if not settings.elasticsearch:
        raise ValueError("Elasticsearch configuration is missing")
    cfg = settings.elasticsearch
    kwargs: Dict[str, Any] = {
        "hosts": cfg.hosts,
    }
    return kwargs


@lru_cache(maxsize=1)
def _cached_client(hosts_key: Tuple[str, ...]) -> AsyncElasticsearch:
    # hosts_key is used purely to make the lru_cache key hashable
    return AsyncElasticsearch(hosts=list(hosts_key))


def get_elasticsearch_client(settings: SaraswatiSettings | None = None) -> AsyncElasticsearch:
    cfg = settings or get_settings()
    kwargs = _build_client_kwargs_from_settings(cfg)
    hosts = tuple(kwargs.get("hosts", []))
    return _cached_client(hosts)
