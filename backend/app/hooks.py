from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine
import asyncio
import logging

import httpx
from fastapi.encoders import jsonable_encoder

from .config import get_settings

logger = logging.getLogger(__name__)


def notify_observers(event_name: str):
    """Decorator factory that notifies configured webhook URLs after the wrapped
    coroutine successfully returns. The decorated function must be async and its
    return value will be included as the `payload` in the POST body.

    The notification is fire-and-forget: failures are logged but do not affect the
    caller's result.
    """

    def decorator(func: Callable[..., Awaitable[Any]]):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("notify_observers decorator can only be applied to async functions")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            print(f"Notifying observers of event '{event_name}' with result: {result}")
            settings = get_settings()
            print(settings)
            hooks = settings.webhooks or []
            print(hooks)
            if not hooks:
                return result

            # Convert the result to a JSON-serializable structure (handles pydantic models, datetimes, etc.)
            serializable_result = jsonable_encoder(result)
            payload = {"event": event_name, "result": serializable_result}

            async def _post(hook):
                # hook is a WebhookConfig pydantic model
                try:
                    # event filtering: empty events list means subscribe to all
                    if hook.events and event_name not in hook.events:
                        return
                    headers = hook.headers or {}
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        print(f"Posting webhook to {hook.url} with payload: {payload} and headers: {headers}")  # Debug print
                        resp = await client.post(str(hook.url), json=payload, headers=headers)
                        resp.raise_for_status()
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.warning("Webhook notification to %s failed: %s", getattr(hook, 'url', hook), exc)

            # schedule all posts concurrently but don't await them here (fire-and-forget)
            asyncio.create_task(_notify_all(hooks, _post))

            return result

        return wrapper

    return decorator


async def _notify_all(urls: list[str], poster: Callable[[str], Coroutine[Any, Any, None]]):
    tasks = [poster(u) for u in urls]
    if not tasks:
        return
    try:
        await asyncio.gather(*tasks)
    except Exception:  # pragma: no cover - best-effort notify
        # individual failures are already logged in _post; swallow here
        pass
