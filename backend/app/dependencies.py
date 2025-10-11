from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends

from .config import SaraswatiSettings, get_settings
from .elasticsearch_client import get_elasticsearch_client
from .repositories.elastic import ElasticsearchNotesRepository
from .repositories.interface import NotesRepositoryProtocol
from .services.notes import NotesService
from .services.reviews import ReviewsService


async def get_app_settings() -> SaraswatiSettings:
    return get_settings()


async def get_notes_repository(
    settings: SaraswatiSettings = Depends(get_app_settings),
) -> AsyncIterator[NotesRepositoryProtocol]:
    if settings.store_backend != "elastic":
        raise ValueError(
            "Only the Elasticsearch backend is supported; update 'store_backend' to 'elastic'."
        )

    client = get_elasticsearch_client(settings)
    yield ElasticsearchNotesRepository(client, settings)


async def get_notes_service(
    repository: NotesRepositoryProtocol = Depends(get_notes_repository),
    settings: SaraswatiSettings = Depends(get_app_settings),
) -> NotesService:
    return NotesService(repository, settings)


async def get_reviews_service(
    repository: NotesRepositoryProtocol = Depends(get_notes_repository),
    settings: SaraswatiSettings = Depends(get_app_settings),
) -> ReviewsService:
    notes_service = NotesService(repository, settings)
    return ReviewsService(repository, notes_service)
