from __future__ import annotations

import logging
from typing import List

import httpx

from ..config import SaraswatiSettings, get_settings

logger = logging.getLogger(__name__)


async def compute_embedding(text: str, settings: SaraswatiSettings | None = None) -> List[float]:
    """Compute an embedding for the provided text using the configured provider."""

    cfg = settings or get_settings()
    if cfg.embedding.provider.lower() != "ollama":
        raise ValueError(f"Unsupported embedding provider: {cfg.embedding.provider}")

    payload = {"model": cfg.embedding.model, "prompt": text}
    base_url = str(cfg.embedding.base_url).rstrip("/")
    async with httpx.AsyncClient(timeout=cfg.embedding.timeout_seconds) as client:
        try:
            response = await client.post(f"{base_url}/api/embeddings", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("Embedding request timed out, returning empty vector", exc_info=exc)
            return []
        except httpx.HTTPError as exc:
            logger.error("Embedding request failed", exc_info=exc)
            raise

        data = response.json()

    vector = data.get("embedding") or data.get("data", [{}])[0].get("embedding")
    if not vector:
        raise ValueError("Embedding response missing 'embedding' field")
    return list(vector)
