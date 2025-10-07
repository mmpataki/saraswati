from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple, Literal, TYPE_CHECKING

from fastapi import HTTPException, status

from ..config import SaraswatiSettings, get_settings
from ..hooks import notify_observers
import logging
from ..models import Note, NoteState, NoteVersion
from ..repositories.interface import NotesRepositoryProtocol
from .embedding import compute_embedding
from .search import hybrid_search

if TYPE_CHECKING:
    from ..models import Review


class NotesService:
    """Business logic for managing Saraswati notes."""

    def __init__(self, repository: NotesRepositoryProtocol, settings: Optional[SaraswatiSettings] = None) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    @notify_observers("note.created")
    async def create_note(
        self,
        author_id: str,
        title: str,
        content: str,
        tags: List[str],
    ) -> Tuple[Note, NoteVersion]:
        vector = await compute_embedding(f"{title}\n{content}", settings=self.settings)
        return await self.repository.create_note_with_version(title, content, tags, author_id, vector)

    @notify_observers("note.draft_updated")
    async def update_draft(
        self,
        version_id: str,
        author_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> NoteVersion:
        version = await self.repository.get_version(version_id)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        if version.state not in {NoteState.DRAFT, NoteState.NEEDS_REVIEW}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version is not editable")
        if version.state == NoteState.DRAFT and version.created_by != author_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit someone else's draft")

        updated_fields = {}
        if title is not None:
            updated_fields["title"] = title
        if content is not None:
            updated_fields["content"] = content
        if tags is not None:
            updated_fields["tags"] = tags

        if content is not None or title is not None:
            vector = await compute_embedding(f"{title or version.title}\n{content or version.content}", settings=self.settings)
            updated_fields["vector"] = vector

        updated_version = await self.repository.update_version(version_id, updated_fields)
        if not updated_version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found after update")
        return updated_version

    @notify_observers("note.review_submitted")
    async def submit_for_review(
        self,
        version_id: str,
        submitter_id: str,
        *,
        review_comment: Optional[str] = None,
    ) -> NoteVersion:
        version = await self.repository.get_version(version_id)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
        if version.state != NoteState.DRAFT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only drafts can be submitted")
        updates = {
            "state": NoteState.NEEDS_REVIEW,
            "submitted_by": submitter_id,
        }
        if review_comment is not None:
            updates["review_comment"] = review_comment
        updated = await self.repository.update_version(version_id, updates)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version missing after submit")
        return updated

    @notify_observers("note.approved")
    async def approve_version(
        self,
        version_id: str,
        reviewer_id: str,
        review_comment: Optional[str] = None,
    ) -> NoteVersion:
        version = await self.repository.get_version(version_id)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
        if version.state != NoteState.NEEDS_REVIEW:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version is not awaiting review")

        updates = {
            "state": NoteState.APPROVED,
            "committed_by": reviewer_id,
            "reviewed_by": reviewer_id,
            "review_comment": review_comment,
        }
        approved = await self.repository.update_version(version_id, updates)
        if not approved:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed to approve version")

        await self.repository.set_note_current_version(approved.note_id, version_id, committed_by=reviewer_id)
        return approved

    async def create_draft_from_current(
        self,
        note_id: str,
        author_id: str,
        updated_content: str,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> NoteVersion:
        note = await self.repository.get_note(note_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
        if not note.current_version_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No approved version to branch from")
        base = await self.repository.get_version(note.current_version_id)
        if not base:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base version not found")
        vector = await compute_embedding(f"{title or base.title}\n{updated_content}", settings=self.settings)

        existing_drafts = await self.repository.get_drafts_by_note_ids([note_id])
        existing = existing_drafts.get(note_id)

        payload_title = title or base.title
        payload_tags = tags or base.tags

        if existing:
            updated_fields = {
                "title": payload_title,
                "content": updated_content,
                "tags": payload_tags,
                "vector": vector,
            }
            updated = await self.repository.update_version(existing.id, updated_fields)
            if not updated:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update draft")
            return updated

        draft = await self.repository.create_new_version(
            note_id,
            base,
            author_id,
            updated_content,
            title=payload_title,
            tags=payload_tags,
            vector=vector,
        )
        return draft

    async def discard_draft(self, note_id: str, author_id: str) -> None:
        note = await self.repository.get_note(note_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

        drafts = await self.repository.get_drafts_by_note_ids([note_id])
        draft = drafts.get(note_id)
        if not draft:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        if draft.created_by != author_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot discard another author's draft")

        await self.repository.delete_version(draft.id)

        # If the discarded draft was marked as the current version, reset to latest approved if available.
        if note.current_version_id == draft.id:
            latest = await self.repository.get_latest_version(note_id)
            replacement = None
            if latest and latest.state == NoteState.APPROVED:
                replacement = latest

            if replacement:
                await self.repository.set_note_current_version(
                    note_id,
                    replacement.id,
                    replacement.committed_by,
                )
            else:
                await self.repository.set_note_current_version(note_id, None, None)

    async def list_review_queue(self) -> List[NoteVersion]:
        return await self.repository.list_review_queue()

    async def list_user_drafts(self, author_id: str) -> List[NoteVersion]:
        return await self.repository.list_user_drafts(author_id)

    async def note_history(self, note_id: str) -> List[NoteVersion]:
        versions = await self.repository.list_note_versions(note_id)
        if not versions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No versions for note")
        return versions

    @notify_observers("note.deleted")
    async def delete_note(self, note_id: str, deleter_id: str) -> None:
        """Mark a note as deleted (soft delete)."""
        result = await self.repository.mark_note_deleted(note_id, deleter_id)
        return result

    async def restore_note(self, note_id: str, restorer_id: str) -> None:
        """Restore a soft-deleted note."""
        await self.repository.mark_note_restored(note_id, restorer_id)

    async def request_note_deletion(
        self,
        note_id: str,
        requester_id: str,
        *,
        reason: Optional[str] = None,
        reviewer_ids: Optional[List[str]] = None,
    ) -> "Review":
        from ..models import Review
        from .reviews import ReviewsService
        
        note = await self.get_note_metadata(note_id)
        if not note.current_version_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete note without published version")
        
        # Import here to avoid circular dependency
        reviews_service = ReviewsService(repository=self.repository, notes_service=self)
        
        # Create a special deletion review - use empty string for draft_version_id to indicate deletion
        review = await reviews_service.repository.create_review(
            note_id=note_id,
            draft_version_id="",  # Empty indicates deletion request
            base_version_id=note.current_version_id,
            title=f"Delete: {note.title}",
            description=reason or f"Request to delete note '{note.title}'",
            created_by=requester_id,
            reviewer_ids=reviewer_ids or [],
            review_type="deletion",
        )
        
        await reviews_service.repository.add_review_event(
            review.id or "",
            event_type="submitted",  # type: ignore
            author_id=requester_id,
            message=reason,
            metadata={"deletion_request": True, "note_id": note_id},
        )
        
        return review

    async def request_note_restore(
        self,
        note_id: str,
        requester_id: str,
        *,
        reason: Optional[str] = None,
        reviewer_ids: Optional[List[str]] = None,
    ) -> "Review":
        from ..models import Review
        from .reviews import ReviewsService

        note = await self.get_note_metadata(note_id)
        # allow restore even if note is currently deleted

        reviews_service = ReviewsService(repository=self.repository, notes_service=self)
        review = await reviews_service.repository.create_review(
            note_id=note_id,
            draft_version_id="",  # empty indicates special operation
            base_version_id=note.current_version_id,
            title=f"Restore: {note.title}",
            description=reason or f"Request to restore note '{note.title}'",
            created_by=requester_id,
            reviewer_ids=reviewer_ids or [],
            review_type="restore",
        )

        await reviews_service.repository.add_review_event(
            review.id or "",
            event_type="submitted",  # type: ignore
            author_id=requester_id,
            message=reason,
            metadata={"restore_request": True, "note_id": note_id},
        )

        return review

    async def get_note_metadata(self, note_id: str) -> Note:
        note = await self.repository.get_note(note_id)
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
        return note

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        return await self.repository.get_notes_by_ids(note_ids)

    async def get_note_detail(self, note_id: str) -> Tuple[Note, NoteVersion]:
        note = await self.get_note_metadata(note_id)
        version = await self._select_display_version(note)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published versions for note")
        return note, version

    async def has_draft(self, note_id: str) -> bool:
        drafts = await self.repository.get_drafts_by_note_ids([note_id])
        return note_id in drafts

    async def vote_note(self, note_id: str, action: Literal["upvote", "downvote"]) -> Tuple[Note, NoteVersion]:
        if action not in {"upvote", "downvote"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported vote action")

        note = await self.repository.update_vote_counts(
            note_id,
            up_delta=1 if action == "upvote" else 0,
            down_delta=1 if action == "downvote" else 0,
        )
        if not note:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

        version = await self._select_display_version(note)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published versions for note")
        return note, version

    async def search(
        self,
        keyword: Optional[str] = None,
        vector: Optional[List[float]] = None,
        *,
        offset: int = 0,
        limit: int = 10,
        include_drafts: bool = False,
        allow_deleted: bool = False,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sort_by: Optional[Literal["relevance", "upvotes", "downvotes"]] = None,
    ) -> Tuple[List[Tuple[NoteVersion, float]], int]:
        # Treat a missing or empty keyword as a wildcard (match_all). This makes an
        # empty query behave the same as "*" from the UI.
        if keyword is None:
            normalized_keyword = ""
        else:
            normalized_keyword = keyword.strip()
            if normalized_keyword == "*":
                normalized_keyword = ""

        resolved_vector = vector
        # If a keyword is present, try to compute its embedding so vector search
        # can participate in the hybrid search. Don't override an explicitly
        # provided vector. If embedding fails, log and continue with keyword-only.
        if normalized_keyword and normalized_keyword != "" and resolved_vector is None:
            try:
                resolved_vector = await compute_embedding(normalized_keyword, settings=self.settings)
            except Exception as exc:  # pragma: no cover - runtime/IO dependent
                logging.getLogger(__name__).warning("Failed to compute embedding for search keyword; proceeding without vector signal", exc_info=exc)

        candidate_limit = max(offset + limit * 5, 500)
        normalized_author = author.strip().lower() if author and author.strip() else None
        normalized_tags: List[str] = []
        if tags:
            normalized_tags = sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})

        raw_results = await hybrid_search(
            self.repository,
            keyword=normalized_keyword,
            vector=resolved_vector,
            candidate_limit=candidate_limit,
        )

        if not raw_results:
            return [], 0

        note_ids = [version.note_id for version, _ in raw_results]
        notes_map = await self.repository.get_notes_by_ids(note_ids)
        drafts_map = await self.repository.get_drafts_by_note_ids(note_ids) if include_drafts else {}

        seen_notes: set[str] = set()
        filtered: List[Tuple[NoteVersion, float]] = []

        for version, score in raw_results:
            note_id = version.note_id
            if note_id in seen_notes:
                continue
            note = notes_map.get(note_id)
            if not note:
                continue
            
            # Filter out deleted notes unless explicitly requested
            if note.deleted_at is not None and not allow_deleted:
                continue

            candidate: Optional[NoteVersion] = None
            if include_drafts:
                draft = drafts_map.get(note_id)
                if draft:
                    candidate = draft

            if candidate is None:
                display_version = await self._select_display_version(note)
                if not display_version or (not include_drafts and display_version.state != NoteState.APPROVED):
                    continue
                candidate = display_version

            candidate_author = (candidate.created_by or note.created_by or "").lower()
            if normalized_author and candidate_author != normalized_author:
                continue

            if normalized_tags:
                candidate_tags = {tag.lower() for tag in (candidate.tags or [])}
                if not all(tag in candidate_tags for tag in normalized_tags):
                    continue

            filtered.append((candidate, score))
            seen_notes.add(note_id)

        total = len(filtered)
        if total == 0:
            return [], 0

        # Support optional sorting modes: relevance (default), upvotes, downvotes.
        if sort_by == "upvotes":
            # sort by note upvotes descending
            note_ids = [v.note_id for v, _ in filtered]
            notes_map = await self.repository.get_notes_by_ids(note_ids)
            filtered.sort(key=lambda it: notes_map.get(it[0].note_id).upvotes if notes_map.get(it[0].note_id) else 0, reverse=True)
        elif sort_by == "downvotes":
            note_ids = [v.note_id for v, _ in filtered]
            notes_map = await self.repository.get_notes_by_ids(note_ids)
            filtered.sort(key=lambda it: notes_map.get(it[0].note_id).downvotes if notes_map.get(it[0].note_id) else 0, reverse=True)

        if offset >= total:
            return [], total

        page_slice = filtered[offset:offset + limit]
        return page_slice, total

    async def get_stats(self) -> Dict[str, int]:
        return await self.repository.get_stats()

    async def get_all_authors(self) -> List[str]:
        """Get all unique authors from approved and needs_review notes."""
        notes = await self.repository.list_notes()
        authors = set()
        for note in notes:
            version = await self._select_display_version(note)
            if version and version.state in {NoteState.APPROVED, NoteState.NEEDS_REVIEW}:
                authors.add(version.created_by)
        return list(authors)

    async def get_all_tags(self) -> List[str]:
        """Get all unique tags from approved and needs_review notes."""
        notes = await self.repository.list_notes()
        tags = set()
        for note in notes:
            version = await self._select_display_version(note)
            if version and version.state in {NoteState.APPROVED, NoteState.NEEDS_REVIEW}:
                tags.update(version.tags)
        return list(tags)

    async def _select_display_version(self, note: Note) -> Optional[NoteVersion]:
        if note.current_version_id:
            version = await self.repository.get_version(note.current_version_id)
            if version:
                return version
        if note.id:
            return await self.repository.get_latest_version(note.id)
        return None
