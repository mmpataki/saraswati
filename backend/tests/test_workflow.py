from __future__ import annotations

import pytest

from app.config import AuthConfig, EmbeddingConfig, MongoConfig, SaraswatiSettings
from app.models import NoteState
from app.repositories.in_memory import InMemoryNotesRepository
from app.services.notes import NotesService


@pytest.fixture()
def settings() -> SaraswatiSettings:
    return SaraswatiSettings(
        environment="test",
        api_prefix="/knowledge/api",
        frontend_base_path="/knowledge",
        auth=AuthConfig(service="http://auth.local", audience="saraswati"),
        mongo=MongoConfig(uri="mongodb://localhost:27017", database="saraswati"),
        embedding=EmbeddingConfig(provider="ollama", base_url="http://localhost:11434", model="nomic-embed-text"),
    )


@pytest.fixture()
def service(settings: SaraswatiSettings, monkeypatch: pytest.MonkeyPatch) -> NotesService:
    repository = InMemoryNotesRepository()

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

    results = await service.search(keyword="keyword")

    assert len(results) == 1
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

    default_results = await service.search(keyword="keyword")
    assert default_results
    default_version, _ = default_results[0]
    assert default_version.id == approved.id
    assert default_version.state == NoteState.APPROVED

    draft_results = await service.search(keyword="keyword", include_drafts=True)
    assert draft_results
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
