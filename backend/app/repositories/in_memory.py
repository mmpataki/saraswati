from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from ..models import (
    Note,
    NoteState,
    NoteVersion,
    Review,
    ReviewDecision,
    ReviewDecisionState,
    ReviewEvent,
    ReviewEventType,
    ReviewStatus,
)


@dataclass
class _StoredNote:
    note: Note
    versions: Dict[str, NoteVersion] = field(default_factory=dict)


class InMemoryNotesRepository:
    """Simple in-memory repository for testing."""

    def __init__(self) -> None:
        self._notes: Dict[str, _StoredNote] = {}
        self._id_counter = itertools.count(1)
        self._reviews: Dict[str, Review] = {}
        self._review_events: Dict[str, List[ReviewEvent]] = {}

    def _new_id(self) -> str:
        return str(next(self._id_counter))

    async def create_note_with_version(
        self,
        title: str,
        content: str,
        tags: List[str],
        author_id: str,
        vector: Optional[List[float]] = None,
    ) -> Tuple[Note, NoteVersion]:
        note_id = self._new_id()
        version_id = self._new_id()
        note = Note(
            _id=note_id,
            title=title,
            created_at=datetime.now(timezone.utc),
            created_by=author_id,
            tags=tags,
            current_version_id=version_id,
            upvotes=0,
            downvotes=0,
        )
        version = NoteVersion(
            _id=version_id,
            note_id=note_id,
            version_index=0,
            title=title,
            content=content,
            tags=tags,
            created_by=author_id,
            state=NoteState.DRAFT,
            vector=vector,
            created_at=datetime.now(timezone.utc),
        )
        self._notes[note_id] = _StoredNote(note=note, versions={version_id: version})
        return note, version

    async def get_note(self, note_id: str) -> Optional[Note]:
        stored = self._notes.get(note_id)
        return stored.note if stored else None

    async def get_version(self, version_id: str) -> Optional[NoteVersion]:
        for stored in self._notes.values():
            if version_id in stored.versions:
                return stored.versions[version_id]
        return None

    async def list_note_versions(self, note_id: str) -> List[NoteVersion]:
        stored = self._notes.get(note_id)
        if not stored:
            return []
        return sorted(stored.versions.values(), key=lambda v: v.version_index)

    async def get_latest_version(self, note_id: str) -> Optional[NoteVersion]:
        stored = self._notes.get(note_id)
        if not stored or not stored.versions:
            return None
        return max(stored.versions.values(), key=lambda v: v.version_index)

    async def list_review_queue(self) -> List[NoteVersion]:
        items: List[NoteVersion] = []
        for stored in self._notes.values():
            for version in stored.versions.values():
                if version.state == NoteState.NEEDS_REVIEW:
                    items.append(version)
        return sorted(items, key=lambda v: v.created_at)

    async def update_version(self, version_id: str, updates: Dict) -> Optional[NoteVersion]:
        version = await self.get_version(version_id)
        if not version:
            return None
        data = version.model_dump(by_alias=True)
        for key, value in updates.items():
            data[key] = value
        updated = NoteVersion.model_validate(data)
        stored = self._notes[updated.note_id]
        stored.versions[version_id] = updated
        return updated

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
        stored = self._notes[note_id]
        version_id = self._new_id()
        next_index = max((v.version_index for v in stored.versions.values()), default=-1) + 1
        version = NoteVersion(
            _id=version_id,
            note_id=note_id,
            version_index=next_index,
            title=title or base_version.title,
            content=content,
            tags=tags or base_version.tags,
            state=NoteState.DRAFT,
            created_by=author_id,
            vector=vector,
            created_at=datetime.now(timezone.utc),
        )
        stored.versions[version_id] = version
        return version

    async def set_note_current_version(
        self,
        note_id: str,
        version_id: Optional[str],
        committed_by: Optional[str],
    ) -> None:
        stored = self._notes[note_id]
        stored.note.current_version_id = version_id
        stored.note.committed_by = committed_by

    async def delete_note(self, note_id: str) -> None:
        self._notes.pop(note_id, None)

    async def mark_note_deleted(self, note_id: str, deleter_id: str) -> None:
        """Mark a note as deleted by setting deleted_at and deleted_by fields."""
        from datetime import datetime, timezone
        stored = self._notes.get(note_id)
        if stored:
            stored.note.deleted_at = datetime.now(timezone.utc)
            stored.note.deleted_by = deleter_id

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        results: Dict[str, Note] = {}
        for note_id in note_ids:
            stored = self._notes.get(note_id)
            if stored and stored.note.id:
                results[note_id] = stored.note
        return results

    async def mark_note_restored(self, note_id: str, restorer_id: str) -> None:
        """Clear deleted_at/deleted_by to restore a note."""
        stored = self._notes.get(note_id)
        if stored:
            stored.note.deleted_at = None
            stored.note.deleted_by = None

    async def update_vote_counts(
        self,
        note_id: str,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
    ) -> Optional[Note]:
        stored = self._notes.get(note_id)
        if not stored:
            return None
        note = stored.note
        note.upvotes = max(0, note.upvotes + up_delta)
        note.downvotes = max(0, note.downvotes + down_delta)
        stored.note = note
        return note

    async def keyword_search(self, query: str, limit: int = 10) -> List[NoteVersion]:
        terms = query.lower().split()
        matches: List[Tuple[NoteVersion, int]] = []
        for stored in self._notes.values():
            for version in stored.versions.values():
                if version.state != NoteState.APPROVED:
                    continue
                haystack = f"{version.title}\n{version.content}".lower()
                score = sum(haystack.count(term) for term in terms)
                if score:
                    matches.append((version, score))
        matches.sort(key=lambda item: item[1], reverse=True)
        return [version for version, _ in matches[:limit]]

    async def vector_search(self, vector: List[float], limit: int = 5) -> List[Tuple[NoteVersion, float]]:
        def cosine(a: List[float], b: List[float]) -> float:
            if not a or not b or len(a) != len(b):
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if not norm_a or not norm_b:
                return 0.0
            return dot / (norm_a * norm_b)

        scored: List[Tuple[NoteVersion, float]] = []
        for stored in self._notes.values():
            for version in stored.versions.values():
                if version.state != NoteState.APPROVED or not version.vector:
                    continue
                scored.append((version, cosine(vector, version.vector)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def get_drafts_by_note_ids(self, note_ids: Iterable[str]) -> Dict[str, NoteVersion]:
        drafts: Dict[str, NoteVersion] = {}
        for note_id in note_ids:
            stored = self._notes.get(note_id)
            if not stored:
                continue
            for version in stored.versions.values():
                if version.state == NoteState.DRAFT:
                    existing = drafts.get(note_id)
                    if not existing or existing.version_index < version.version_index:
                        drafts[note_id] = version
        return drafts

    async def delete_version(self, version_id: str) -> None:
        for stored in self._notes.values():
            if version_id in stored.versions:
                del stored.versions[version_id]
                return

    async def list_user_drafts(self, author_id: str, limit: int = 50) -> List[NoteVersion]:
        drafts: List[NoteVersion] = []
        for stored in self._notes.values():
            for version in stored.versions.values():
                if version.state == NoteState.DRAFT and version.created_by == author_id:
                    drafts.append(version)
        drafts.sort(key=lambda v: v.created_at, reverse=True)
        return drafts[:limit]

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
        review_id = self._new_id()
        now = datetime.now(timezone.utc)
        review = Review(
            _id=review_id,
            note_id=note_id,
            draft_version_id=draft_version_id,
            base_version_id=base_version_id,
            title=title,
            description=description,
            created_by=created_by,
            reviewer_ids=reviewer_ids or [],
            type=review_type,
            status=ReviewStatus.OPEN,
            review_decisions={},
            merge_version_id=None,
            merged_by=None,
            created_at=now,
            updated_at=now,
            merged_at=None,
            closed_at=None,
        )
        self._reviews[review_id] = review
        self._review_events.setdefault(review_id, [])
        return review

    async def update_review(self, review_id: str, updates: Dict[str, object]) -> Optional[Review]:
        review = self._reviews.get(review_id)
        if not review:
            return None
        data = review.model_dump()
        for key, value in updates.items():
            if isinstance(value, ReviewStatus):
                data[key] = value.value
            elif key == "review_decisions" and isinstance(value, dict):
                decisions: Dict[str, ReviewDecisionState] = {}
                for user_id, state in value.items():
                    if isinstance(state, ReviewDecisionState):
                        decisions[user_id] = state
                    elif isinstance(state, dict):
                        decisions[user_id] = ReviewDecisionState(
                            decision=ReviewDecision(state.get("decision")),
                            comment=state.get("comment"),
                            updated_at=state.get("updated_at", datetime.now(timezone.utc)),
                        )
                data[key] = decisions
            elif isinstance(value, ReviewDecisionState):
                data[key] = value
            else:
                data[key] = value
        updated = Review.model_validate(data)
        self._reviews[review_id] = updated
        return updated

    async def get_review(self, review_id: str) -> Optional[Review]:
        return self._reviews.get(review_id)

    async def get_review_by_version(self, draft_version_id: str) -> Optional[Review]:
        for review in self._reviews.values():
            if review.draft_version_id == draft_version_id:
                return review
        return None

    async def get_reviews_by_version_ids(self, version_ids: Iterable[str]) -> Dict[str, Review]:
        targets = {version_id for version_id in version_ids}
        results: Dict[str, Review] = {}
        for review in self._reviews.values():
            if review.draft_version_id in targets:
                results[review.draft_version_id] = review
        return results

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
        items: List[Review] = []
        for review in self._reviews.values():
            if status and review.status not in status:
                continue
            if created_by and review.created_by != created_by:
                continue
            if reviewer_id and reviewer_id not in review.reviewer_ids:
                continue
            if note_id and review.note_id != note_id:
                continue
            if involved_user and involved_user not in {review.created_by, *review.reviewer_ids}:
                continue
            items.append(review)
        items.sort(key=lambda entry: entry.updated_at, reverse=True)
        return items[:limit]

    async def add_review_event(
        self,
        review_id: str,
        event_type: ReviewEventType,
        *,
        author_id: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ReviewEvent:
        event_id = self._new_id()
        event = ReviewEvent(
            _id=event_id,
            review_id=review_id,
            event_type=event_type,
            author_id=author_id,
            message=message,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        self._review_events.setdefault(review_id, []).append(event)
        return event

    async def list_review_events(self, review_id: str, limit: int = 200) -> List[ReviewEvent]:
        events = self._review_events.get(review_id, [])
        return events[:limit]
