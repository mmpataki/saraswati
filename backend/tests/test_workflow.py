from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import pytest

from app.config import EmbeddingConfig, ElasticsearchConfig, ExternalAuthConfig, SaraswatiSettings
from app.models import (
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
from app.services.notes import NotesService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = sum(x * x for x in a_list) ** 0.5
    norm_b = sum(y * y for y in b_list) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class FakeNotesRepository:
    """Minimal in-memory repository used for service workflow tests."""

    def __init__(self) -> None:
        self._note_counter = itertools.count(1)
        self._version_counter = itertools.count(1)
        self._review_counter = itertools.count(1)
        self._event_counter = itertools.count(1)
        self._notes: Dict[str, Note] = {}
        self._versions: Dict[str, NoteVersion] = {}
        self._reviews: Dict[str, Review] = {}
        self._review_events: Dict[str, List[ReviewEvent]] = {}

    async def create_note_with_version(
        self,
        title: str,
        content: str,
        tags: List[str],
        author_id: str,
        vector: Optional[List[float]] = None,
    ) -> Tuple[Note, NoteVersion]:
        note_id = str(next(self._note_counter))
        version_id = str(next(self._version_counter))
        now = _now()
        note = Note(
            id=note_id,
            title=title,
            created_by=author_id,
            created_at=now,
            tags=list(tags),
            current_version_id=version_id,
        )
        version = NoteVersion(
            id=version_id,
            note_id=note_id,
            version_index=0,
            title=title,
            content=content,
            tags=list(tags),
            state=NoteState.DRAFT,
            created_by=author_id,
            created_at=now,
            vector=vector,
        )
        self._notes[note_id] = note
        self._versions[version_id] = version
        return note, version

    async def get_note(self, note_id: str) -> Optional[Note]:
        return self._notes.get(note_id)

    async def get_version(self, version_id: str) -> Optional[NoteVersion]:
        return self._versions.get(version_id)

    async def get_latest_version(self, note_id: str) -> Optional[NoteVersion]:
        versions = [v for v in self._versions.values() if v.note_id == note_id]
        if not versions:
            return None
        return max(versions, key=lambda version: version.version_index)

    async def list_note_versions(self, note_id: str) -> List[NoteVersion]:
        versions = [v for v in self._versions.values() if v.note_id == note_id]
        return sorted(versions, key=lambda version: version.version_index)

    async def list_review_queue(self) -> List[NoteVersion]:
        return [v for v in self._versions.values() if v.state == NoteState.NEEDS_REVIEW]

    async def update_version(self, version_id: str, updates: Dict[str, object]) -> Optional[NoteVersion]:
        version = self._versions.get(version_id)
        if not version:
            return None
        payload = version.model_dump()
        for key, value in updates.items():
            if isinstance(value, NoteState):
                payload[key] = value.value
            elif isinstance(value, ReviewDecisionState):
                payload.setdefault("review_decisions", {})  # type: ignore[assignment]
                payload[key] = value
            else:
                payload[key] = value
        updated = NoteVersion.model_validate(payload)
        self._versions[version_id] = updated
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
        existing = [v for v in self._versions.values() if v.note_id == note_id]
        next_index = max((v.version_index for v in existing), default=-1) + 1
        version_id = str(next(self._version_counter))
        version = NoteVersion(
            id=version_id,
            note_id=note_id,
            version_index=next_index,
            title=title or base_version.title,
            content=content,
            tags=list(tags or base_version.tags),
            state=NoteState.DRAFT,
            created_by=author_id,
            created_at=_now(),
            vector=vector,
        )
        self._versions[version_id] = version
        return version

    async def set_note_current_version(
        self,
        note_id: str,
        version_id: Optional[str],
        committed_by: Optional[str],
    ) -> None:
        note = self._notes.get(note_id)
        if not note:
            return
        updated = note.model_copy(update={"current_version_id": version_id, "committed_by": committed_by})
        self._notes[note_id] = updated

    async def delete_note(self, note_id: str) -> None:
        self._notes.pop(note_id, None)
        to_delete = [version_id for version_id, version in self._versions.items() if version.note_id == note_id]
        for version_id in to_delete:
            self._versions.pop(version_id, None)

    async def mark_note_deleted(self, note_id: str, deleter_id: str) -> None:
        note = self._notes.get(note_id)
        if not note:
            return
        updated = note.model_copy(update={"deleted_at": _now(), "deleted_by": deleter_id})
        self._notes[note_id] = updated

    async def mark_note_restored(self, note_id: str, restorer_id: str) -> None:
        note = self._notes.get(note_id)
        if not note:
            return
        updated = note.model_copy(update={"deleted_at": None, "deleted_by": None, "committed_by": restorer_id})
        self._notes[note_id] = updated

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        return {note_id: self._notes[note_id] for note_id in note_ids if note_id in self._notes}

    async def update_vote_counts(
        self,
        note_id: str,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
    ) -> Optional[Note]:
        note = self._notes.get(note_id)
        if not note:
            return None
        new_up = max(0, note.upvotes + up_delta)
        new_down = max(0, note.downvotes + down_delta)
        updated = note.model_copy(update={"upvotes": new_up, "downvotes": new_down})
        self._notes[note_id] = updated
        return updated

    async def hybrid_search(
        self,
        *,
        keyword: Optional[str] = None,
        vector: Optional[List[float]] = None,
        limit: int = 50,
        states: Optional[List[NoteState]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        committed_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
    ) -> Tuple[List[Tuple[NoteVersion, float]], int, Dict[str, List[str]]]:
        allowed_states = {state.value for state in (states or [NoteState.APPROVED])}
        keyword_token = (keyword or "").strip().lower()
        tag_filters = {tag for tag in (tags or []) if tag}

        scored: List[Tuple[NoteVersion, float]] = []
        for version in self._versions.values():
            if allowed_states and version.state.value not in allowed_states:
                continue
            if author and version.created_by != author:
                continue
            if committed_by and version.committed_by != committed_by:
                continue
            if reviewed_by and version.reviewed_by != reviewed_by:
                continue
            if tag_filters and not tag_filters.issubset(set(version.tags)):
                continue

            score = 0.0
            if vector and version.vector:
                score = max(score, max(_cosine_similarity(version.vector, vector), 0.0))

            if keyword_token:
                haystack = "\n".join([version.title, version.content, " ".join(version.tags)]).lower()
                if keyword_token in haystack:
                    score = max(score, 0.5)
                else:
                    continue

            if score == 0.0:
                score = 1.0

            scored.append((version, score))

        scored.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
        total = len(scored)
        limited = scored[:limit]

        authors = sorted({version.created_by for version, _ in scored if version.created_by})
        committers = sorted({version.committed_by for version, _ in scored if version.committed_by})
        reviewers = sorted({version.reviewed_by for version, _ in scored if version.reviewed_by})
        tags_facet = sorted({tag for version, _ in scored for tag in version.tags})

        facets = {
            "authors": authors,
            "committers": committers,
            "reviewers": reviewers,
            "tags": tags_facet,
        }
        return limited, total, facets

    async def keyword_search(
        self,
        query: str,
        limit: int = 10,
        *,
        states: Optional[List[NoteState]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        committed_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
    ) -> List[NoteVersion]:
        normalized_states = {state.value for state in (states or [NoteState.APPROVED])}
        normalized_query = (query or "").strip().lower()
        normalized_author = author.lower() if author else None
        normalized_committer = committed_by.lower() if committed_by else None
        normalized_reviewer = reviewed_by.lower() if reviewed_by else None
        normalized_tags = {tag.lower() for tag in (tags or []) if tag}

        matches: List[NoteVersion] = []
        for version in self._versions.values():
            if version.state.value not in normalized_states:
                continue
            if normalized_query and normalized_query not in version.title.lower() and normalized_query not in version.content.lower():
                continue
            if normalized_author and version.created_by.lower() != normalized_author:
                continue
            if normalized_committer and (version.committed_by or "").lower() != normalized_committer:
                continue
            if normalized_reviewer and (version.reviewed_by or "").lower() != normalized_reviewer:
                continue
            if normalized_tags and not normalized_tags.issubset({tag.lower() for tag in version.tags}):
                continue
            matches.append(version)

        matches.sort(key=lambda version: (version.created_at, version.version_index), reverse=True)
        return matches[:limit]

    async def vector_search(
        self,
        vector: List[float],
        limit: int = 5,
        *,
        states: Optional[List[NoteState]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        committed_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
    ) -> List[Tuple[NoteVersion, float]]:
        normalized_states = {state.value for state in (states or [NoteState.APPROVED])}
        normalized_author = author.lower() if author else None
        normalized_committer = committed_by.lower() if committed_by else None
        normalized_reviewer = reviewed_by.lower() if reviewed_by else None
        normalized_tags = {tag.lower() for tag in (tags or []) if tag}

        results: List[Tuple[NoteVersion, float]] = []
        for version in self._versions.values():
            if version.state.value not in normalized_states:
                continue
            if normalized_author and version.created_by.lower() != normalized_author:
                continue
            if normalized_committer and (version.committed_by or "").lower() != normalized_committer:
                continue
            if normalized_reviewer and (version.reviewed_by or "").lower() != normalized_reviewer:
                continue
            if normalized_tags and not normalized_tags.issubset({tag.lower() for tag in version.tags}):
                continue
            if not version.vector:
                continue
            score = _cosine_similarity(version.vector, vector)
            results.append((version, score))

        results.sort(key=lambda item: item[1], reverse=True)
        return results[:limit]

    async def get_drafts_by_note_ids(self, note_ids: Iterable[str]) -> Dict[str, NoteVersion]:
        result: Dict[str, NoteVersion] = {}
        for version in self._versions.values():
            if version.note_id in note_ids and version.state == NoteState.DRAFT:
                result.setdefault(version.note_id, version)
        return result

    async def delete_version(self, version_id: str) -> None:
        version = self._versions.pop(version_id, None)
        if not version:
            return
        note = self._notes.get(version.note_id)
        if not note:
            return
        if note.current_version_id == version_id:
            updated = note.model_copy(update={"current_version_id": None})
            self._notes[note.id or version.note_id] = updated

    async def list_user_drafts(self, author_id: str, limit: int = 50) -> List[NoteVersion]:
        drafts = [v for v in self._versions.values() if v.state == NoteState.DRAFT and v.created_by == author_id]
        drafts.sort(key=lambda version: version.created_at, reverse=True)
        return drafts[:limit]

    async def list_notes(self, *, skip: int = 0, limit: int = 50) -> List[Note]:
        notes = sorted(self._notes.values(), key=lambda note: note.created_at, reverse=True)
        return notes[skip:skip + limit]

    async def count_notes(self) -> int:
        return len(self._notes)

    async def get_stats(self) -> Dict[str, int]:
        return {
            "notes": len(self._notes),
            "versions": len(self._versions),
        }

    async def list_committers(self) -> List[str]:
        return sorted({version.committed_by for version in self._versions.values() if version.committed_by})

    async def list_reviewers(self) -> List[str]:
        return sorted({version.reviewed_by for version in self._versions.values() if version.reviewed_by})

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
        review_id = str(next(self._review_counter))
        review = Review(
            id=review_id,
            note_id=note_id,
            draft_version_id=draft_version_id,
            base_version_id=base_version_id,
            title=title,
            description=description,
            created_by=created_by,
            reviewer_ids=list(reviewer_ids or []),
            status=ReviewStatus.OPEN,
            type=review_type,
        )
        self._reviews[review_id] = review
        self._review_events.setdefault(review_id, [])
        return review

    async def update_review(self, review_id: str, updates: Dict[str, object]) -> Optional[Review]:
        review = self._reviews.get(review_id)
        if not review:
            return None
        payload = review.model_dump()
        for key, value in updates.items():
            if isinstance(value, ReviewStatus):
                payload[key] = value.value
            elif isinstance(value, dict):
                payload[key] = value
            else:
                payload[key] = value
        payload["updated_at"] = _now()
        updated = Review.model_validate(payload)
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
        id_set = set(version_ids)
        return {review.draft_version_id: review for review in self._reviews.values() if review.draft_version_id in id_set}

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
        statuses = {s.value for s in (status or [])}
        results: List[Review] = []
        for review in self._reviews.values():
            if statuses and review.status.value not in statuses:
                continue
            if created_by and review.created_by != created_by:
                continue
            if reviewer_id and reviewer_id not in review.reviewer_ids:
                continue
            if note_id and review.note_id != note_id:
                continue
            if involved_user and involved_user not in {review.created_by, *review.reviewer_ids}:
                continue
            results.append(review)
        results.sort(key=lambda review: review.updated_at, reverse=True)
        return results[:limit]

    async def add_review_event(
        self,
        review_id: str,
        event_type: ReviewEventType,
        *,
        author_id: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ReviewEvent:
        event_id = str(next(self._event_counter))
        event = ReviewEvent(
            id=event_id,
            review_id=review_id,
            event_type=event_type,
            author_id=author_id,
            message=message,
            metadata=dict(metadata or {}),
            created_at=_now(),
        )
        self._review_events.setdefault(review_id, []).append(event)
        return event

    async def list_review_events(self, review_id: str, limit: int = 200) -> List[ReviewEvent]:
        return self._review_events.get(review_id, [])[:limit]


@pytest.fixture()
def settings() -> SaraswatiSettings:
    return SaraswatiSettings(
        environment="test",
        api_prefix="/knowledge/api",
        frontend_base_path="/knowledge",
        auth_system="introspect",
        auth_external=ExternalAuthConfig(service="http://auth.local"),
        elasticsearch=ElasticsearchConfig(
            hosts=["http://localhost:9200"],
            notes_index="notes",
            versions_index="note_versions",
            reviews_index="note_reviews",
            review_events_index="note_review_events",
            users_index="users",
        ),
        embedding=EmbeddingConfig(provider="ollama", base_url="http://localhost:11434", model="nomic-embed-text"),
    )


@pytest.fixture()
def service(settings: SaraswatiSettings, monkeypatch: pytest.MonkeyPatch) -> NotesService:
    repository = FakeNotesRepository()

    async def fake_embedding(_: str, settings=None):  # pragma: no cover - deterministic stub
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("app.services.notes.compute_embedding", fake_embedding)
    return NotesService(repository, settings)


@pytest.mark.asyncio
async def test_note_lifecycle(service: NotesService) -> None:
    note, draft = await service.create_note("alice", "First Note", "# Hello", ["intro"])
    assert draft.state == NoteState.DRAFT
    assert note.upvotes == 0
    assert note.downvotes == 0

    submitted = await service.submit_for_review(draft.id, submitter_id="alice")
    assert submitted.state == NoteState.NEEDS_REVIEW

    approved = await service.approve_version(submitted.id, reviewer_id="bob")
    assert approved.state == NoteState.APPROVED
    assert approved.committed_by == "bob"

    history = await service.note_history(note.id)
    assert len(history) == 1

    new_draft = await service.create_draft_from_current(note.id, author_id="alice", updated_content="# Hello World")
    assert new_draft.state == NoteState.DRAFT

    updated = await service.update_draft(new_draft.id, author_id="alice", content="# Updated")
    assert updated.content == "# Updated"


@pytest.mark.asyncio
async def test_vote_counts(service: NotesService) -> None:
    note, _ = await service.create_note("carol", "Vote Note", "Content", ["tag"])

    updated_note, _ = await service.vote_note(note.id, action="upvote")
    assert updated_note.upvotes == 1
    assert updated_note.downvotes == 0

    updated_note, _ = await service.vote_note(note.id, action="downvote")
    assert updated_note.upvotes == 1
    assert updated_note.downvotes == 1


@pytest.mark.asyncio
async def test_search_returns_latest_approved_version(service: NotesService) -> None:
    note, draft = await service.create_note("dave", "Searchable Note", "Original content", ["alpha"])

    submitted = await service.submit_for_review(draft.id, submitter_id="dave")
    first_approved = await service.approve_version(submitted.id, reviewer_id="erica")
    assert first_approved.state == NoteState.APPROVED

    draft_two = await service.create_draft_from_current(
        note.id,
        author_id="dave",
        updated_content="Updated content with keyword",
        title="Refined Searchable Note",
        tags=["alpha", "beta"],
    )

    updated_draft_two = await service.update_draft(
        draft_two.id,
        author_id="dave",
        title="Refined Searchable Note",
        content="Updated content with keyword",
        tags=["alpha", "beta"],
    )
    assert updated_draft_two.state == NoteState.DRAFT

    submitted_two = await service.submit_for_review(updated_draft_two.id, submitter_id="dave")
    second_approved = await service.approve_version(submitted_two.id, reviewer_id="erica")
    assert second_approved.state == NoteState.APPROVED
    assert second_approved.version_index > first_approved.version_index

    results, total, facets = await service.search(keyword="keyword")

    assert total == 1
    assert list(facets.keys())
    version, score = results[0]
    assert version.id == second_approved.id
    assert score > 0


@pytest.mark.asyncio
async def test_single_draft_per_note(service: NotesService) -> None:
    note, draft = await service.create_note("frank", "Draft Control", "Initial", ["alpha"])
    submitted = await service.submit_for_review(draft.id, submitter_id="frank")
    await service.approve_version(submitted.id, reviewer_id="grace")
    assert not await service.has_draft(note.id)

    first_draft = await service.create_draft_from_current(
        note.id,
        author_id="frank",
        updated_content="First draft content",
        title="Draft Control",
        tags=["alpha", "beta"],
    )

    assert await service.has_draft(note.id)

    second_draft = await service.create_draft_from_current(
        note.id,
        author_id="frank",
        updated_content="Second draft content",
        title="Draft Control Updated",
        tags=["alpha", "beta"],
    )

    assert first_draft.id == second_draft.id
    assert second_draft.content == "Second draft content"
    history = await service.note_history(note.id)
    draft_versions = [version for version in history if version.state == NoteState.DRAFT]
    assert len(draft_versions) == 1


@pytest.mark.asyncio
async def test_search_include_drafts(service: NotesService) -> None:
    note, draft = await service.create_note("hank", "Search Draft", "Original keyword text", ["gamma"])
    submitted = await service.submit_for_review(draft.id, submitter_id="hank")
    approved = await service.approve_version(submitted.id, reviewer_id="iris")

    draft_version = await service.create_draft_from_current(
        note.id,
        author_id="hank",
        updated_content="Draft keyword update",
        title="Search Draft",
        tags=["gamma", "delta"],
    )

    default_results, default_total, _ = await service.search(keyword="keyword")
    assert default_total
    default_version, _ = default_results[0]
    assert default_version.id == approved.id
    assert default_version.state == NoteState.APPROVED

    draft_results, draft_total, _ = await service.search(keyword="keyword", include_drafts=True)
    assert draft_total
    draft_result_version, _ = draft_results[0]
    assert draft_result_version.id == draft_version.id
    assert draft_result_version.state == NoteState.DRAFT


@pytest.mark.asyncio
async def test_discard_draft(service: NotesService) -> None:
    note, draft = await service.create_note("ivy", "Discardable", "Initial", ["zeta"])
    submitted = await service.submit_for_review(draft.id, submitter_id="ivy")
    approved = await service.approve_version(submitted.id, reviewer_id="john")
    assert approved.state == NoteState.APPROVED

    new_draft = await service.create_draft_from_current(
        note.id,
        author_id="ivy",
        updated_content="Draft edits",
        title="Discardable",
        tags=["zeta", "eta"],
    )
    assert await service.has_draft(note.id)

    await service.discard_draft(note.id, author_id="ivy")

    assert not await service.has_draft(note.id)
    history = await service.note_history(note.id)
    draft_states = [version for version in history if version.state == NoteState.DRAFT]
    assert draft_states == []

    detail_note, display_version = await service.get_note_detail(note.id)
    assert detail_note.current_version_id == approved.id
    assert display_version.id == approved.id
