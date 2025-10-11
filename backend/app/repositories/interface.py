from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Protocol, Tuple

from ..models import (
    Note,
    NoteState,
    NoteVersion,
    Review,
    ReviewEvent,
    ReviewEventType,
    ReviewStatus,
)


class NotesRepositoryProtocol(Protocol):
    async def create_note_with_version(
        self,
        title: str,
        content: str,
        tags: List[str],
        author_id: str,
        vector: Optional[List[float]] = None,
    ) -> Tuple[Note, NoteVersion]:
        ...

    async def get_note(self, note_id: str) -> Optional[Note]:
        ...

    async def get_version(self, version_id: str) -> Optional[NoteVersion]:
        ...

    async def get_latest_version(self, note_id: str) -> Optional[NoteVersion]:
        ...

    async def list_note_versions(self, note_id: str) -> List[NoteVersion]:
        ...

    async def list_review_queue(self) -> List[NoteVersion]:
        ...

    async def update_version(self, version_id: str, updates: Dict[str, object]) -> Optional[NoteVersion]:
        ...

    async def create_new_version(
        self,
        note_id: str,
        base_version: NoteVersion,
        author_id: str,
        content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        vector: Optional[List[float]] = None,
    ) -> NoteVersion:
        ...

    async def set_note_current_version(
        self,
        note_id: str,
        version_id: Optional[str],
        committed_by: Optional[str],
    ) -> None:
        ...

    async def delete_note(self, note_id: str) -> None:
        ...

    async def mark_note_deleted(self, note_id: str, deleter_id: str) -> None:
        ...

    async def mark_note_restored(self, note_id: str, restorer_id: str) -> None:
        ...

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        ...

    async def update_vote_counts(
        self,
        note_id: str,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
    ) -> Optional[Note]:
        ...

    async def hybrid_search(
        self,
        *,
        keyword: Optional[str] = None,
        vector: Optional[List[float]] = None,
        limit: int = 50,
        include_drafts: bool = False,
        allow_deleted: bool = False,
        states: Optional[List[NoteState]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        committed_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        sort_by: Optional[str] = None,
    ) -> Tuple[List[Tuple[NoteVersion, float]], int, Dict[str, List[str]]]:
        ...

    async def get_drafts_by_note_ids(self, note_ids: Iterable[str]) -> Dict[str, NoteVersion]:
        ...

    async def delete_version(self, version_id: str) -> None:
        ...

    async def list_user_drafts(self, author_id: str, limit: int = 50) -> List[NoteVersion]:
        ...

    async def list_notes(self, *, skip: int = 0, limit: int = 50) -> List[Note]:
        ...

    async def count_notes(self) -> int:
        ...

    async def get_stats(self) -> Dict[str, int]:
        ...

    async def create_review(
        self,
        note_id: str,
        draft_version_id: str,
        *,
        base_version_id: Optional[str],
        title: str,
        description: Optional[str],
        created_by: str,
        reviewer_ids: Optional[List[str]] = None,
        review_type: Optional[str] = None,
    ) -> Review:
        ...

    async def update_review(self, review_id: str, updates: Dict[str, object]) -> Optional[Review]:
        ...

    async def get_review(self, review_id: str) -> Optional[Review]:
        ...

    async def get_review_by_version(self, draft_version_id: str) -> Optional[Review]:
        ...

    async def get_reviews_by_version_ids(self, version_ids: Iterable[str]) -> Dict[str, Review]:
        ...

    async def list_reviews(
        self,
        *,
        status: Optional[List[ReviewStatus]] = None,
        created_by: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        involved_user: Optional[str] = None,
        note_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Review]:
        ...

    async def add_review_event(
        self,
        review_id: str,
        event_type: ReviewEventType,
        *,
        author_id: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ReviewEvent:
        ...

    async def list_review_events(self, review_id: str, limit: int = 200) -> List[ReviewEvent]:
        ...
