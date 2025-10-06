from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status

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
from ..repositories.interface import NotesRepositoryProtocol
from .notes import NotesService


_ACTIVE_STATUSES = {ReviewStatus.OPEN, ReviewStatus.CHANGES_REQUESTED}


class ReviewsService:
    """Orchestrates the GitHub-style review workflow for Saraswati notes."""

    def __init__(self, repository: NotesRepositoryProtocol, notes_service: NotesService) -> None:
        self.repository = repository
        self.notes_service = notes_service

    async def submit_version_for_review(
        self,
        version_id: str,
        submitter_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reviewer_ids: Optional[List[str]] = None,
        summary_comment: Optional[str] = None,
    ) -> Tuple[NoteVersion, Review]:
        version = await self.notes_service.submit_for_review(
            version_id,
            submitter_id,
            review_comment=summary_comment,
        )
        note = await self.notes_service.get_note_metadata(version.note_id)
        base_version_id = note.current_version_id if note.current_version_id and note.current_version_id != version.id else None

        existing = await self.repository.get_review_by_version(version.id)
        now = datetime.now(timezone.utc)
        resolved_title = title or version.title
        resolved_description = description if description is not None else (existing.description if existing else None)
        resolved_reviewers = reviewer_ids if reviewer_ids is not None else (existing.reviewer_ids if existing else [])

        if existing:
            trimmed_decisions: Dict[str, ReviewDecisionState] = {
                user_id: state
                for user_id, state in existing.review_decisions.items()
                if state.decision != ReviewDecision.CHANGES_REQUESTED
            }
            updates: Dict[str, object] = {
                "title": resolved_title,
                "description": resolved_description,
                "reviewer_ids": resolved_reviewers,
                "status": ReviewStatus.OPEN,
                "updated_at": now,
                "review_decisions": trimmed_decisions,
                "base_version_id": base_version_id,
            }
            review = await self.repository.update_review(existing.id or "", updates)
            if not review:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update review")
        else:
            review = await self.repository.create_review(
                note_id=note.id or version.note_id,
                draft_version_id=version.id or "",
                base_version_id=base_version_id,
                title=resolved_title,
                description=resolved_description,
                created_by=submitter_id,
                reviewer_ids=resolved_reviewers,
            )

        await self.repository.add_review_event(
            review.id or "",
            event_type=ReviewEventType.SUBMITTED,
            author_id=submitter_id,
            message=summary_comment,
            metadata={"draft_version_id": version.id},
        )

        refreshed = await self.repository.get_review(review.id or "")
        return version, refreshed or review

    async def comment_on_review(self, review_id: str, author_id: str, message: str) -> ReviewEvent:
        review = await self._require_review(review_id)
        if review.status == ReviewStatus.MERGED and not message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required after merge")
        return await self.repository.add_review_event(
            review_id,
            event_type=ReviewEventType.COMMENT,
            author_id=author_id,
            message=message,
        )

    async def approve_review(self, review_id: str, reviewer_id: str, comment: Optional[str] = None) -> Review:
        review = await self._require_review(review_id)
        if review.status in {ReviewStatus.MERGED, ReviewStatus.CLOSED}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review is no longer open")
        if review.created_by == reviewer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review creator cannot approve their own review")

        updated_decisions = dict(review.review_decisions)
        updated_decisions[reviewer_id] = ReviewDecisionState(
            decision=ReviewDecision.APPROVED,
            comment=comment,
            updated_at=datetime.now(timezone.utc),
        )
        updated_review = await self.repository.update_review(
            review_id,
            {
                "review_decisions": updated_decisions,
                "status": ReviewStatus.OPEN,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to approve review")

        await self.repository.add_review_event(
            review_id,
            ReviewEventType.APPROVED,
            author_id=reviewer_id,
            message=comment,
        )
        return updated_review

    async def request_changes(self, review_id: str, reviewer_id: str, comment: Optional[str] = None) -> Review:
        review = await self._require_review(review_id)
        if review.status == ReviewStatus.MERGED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Merged reviews cannot request changes")

        # For deletion reviews, there's no draft version to check
        if review.draft_version_id:
            version = await self.repository.get_version(review.draft_version_id)
            if not version:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft version missing for review")

        updated_decisions = dict(review.review_decisions)
        updated_decisions[reviewer_id] = ReviewDecisionState(
            decision=ReviewDecision.CHANGES_REQUESTED,
            comment=comment,
            updated_at=datetime.now(timezone.utc),
        )
        updated_review = await self.repository.update_review(
            review_id,
            {
                "review_decisions": updated_decisions,
                "status": ReviewStatus.CHANGES_REQUESTED,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to request changes")

        # Only update draft version if this is not a deletion review
        if review.draft_version_id:
            await self.repository.update_version(
                review.draft_version_id,
                {
                    "state": NoteState.DRAFT,
                    "submitted_by": None,
                },
            )

        await self.repository.add_review_event(
            review_id,
            ReviewEventType.CHANGES_REQUESTED,
            author_id=reviewer_id,
            message=comment,
        )
        return updated_review

    async def close_review(self, review_id: str, actor_id: str, message: Optional[str] = None) -> Review:

        review = await self._require_review(review_id)
        if review.status == ReviewStatus.MERGED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot close a merged review")

        # Only update draft version if this is not a deletion review
        if review.draft_version_id:
            version = await self.repository.get_version(review.draft_version_id)
            if version:
                await self.repository.update_version(
                    review.draft_version_id,
                    {
                        "state": NoteState.DRAFT,
                        "submitted_by": None,
                    },
                )

        updated_review = await self.repository.update_review(
            review_id,
            {
                "status": ReviewStatus.CLOSED,
                "closed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to close review")

        await self.repository.add_review_event(
            review_id,
            ReviewEventType.CLOSED,
            author_id=actor_id,
            message=message,
        )
        return updated_review

    async def reopen_review(self, review_id: str, actor_id: str, message: Optional[str] = None) -> Review:
        review = await self._require_review(review_id)
        if review.status not in {ReviewStatus.CLOSED, ReviewStatus.CHANGES_REQUESTED}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review is already open")

        # Only update draft version if this is not a deletion review
        if review.draft_version_id:
            await self.repository.update_version(
                review.draft_version_id,
                {
                    "state": NoteState.NEEDS_REVIEW,
                    "submitted_by": actor_id,
                },
            )
        updated_review = await self.repository.update_review(
            review_id,
            {
                "status": ReviewStatus.OPEN,
                "closed_at": None,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reopen review")

        await self.repository.add_review_event(
            review_id,
            ReviewEventType.REOPENED,
            author_id=actor_id,
            message=message,
        )
        return updated_review

    async def update_review(
        self,
        review_id: str,
        actor_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reviewer_ids: Optional[List[str]] = None,
    ) -> Review:
        review = await self._require_review(review_id)
        if review.status in {ReviewStatus.MERGED, ReviewStatus.CLOSED}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review can no longer be updated")

        # For deletion reviews, check permissions differently
        allowed_actors = {review.created_by}
        if review.draft_version_id:
            version = await self.repository.get_version(review.draft_version_id)
            if not version:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft version missing for review")
            allowed_actors.update({
                version.created_by,
                version.submitted_by,
            })
        else:
            # For deletion reviews, only the creator can update
            version = None
        if actor_id not in {value for value in allowed_actors if value}:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to modify this review")

        updates: Dict[str, object] = {}
        metadata: Dict[str, object] = {}

        if title is not None:
            trimmed_title = title.strip()
            if not trimmed_title:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty")
            if trimmed_title != review.title:
                updates["title"] = trimmed_title
                metadata["title"] = trimmed_title

        if description is not None and description != review.description:
            updates["description"] = description
            metadata["description"] = description

        if reviewer_ids is not None:
            normalized_reviewers: List[str] = list(dict.fromkeys([rid.strip() for rid in reviewer_ids if rid.strip()]))
            if not normalized_reviewers:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one reviewer is required")
            if normalized_reviewers != review.reviewer_ids:
                updates["reviewer_ids"] = normalized_reviewers
                retained_decisions = {
                    user_id: state
                    for user_id, state in review.review_decisions.items()
                    if user_id in normalized_reviewers
                }
                updates["review_decisions"] = retained_decisions
                existing = set(review.reviewer_ids)
                new = set(normalized_reviewers)
                added = sorted(new - existing)
                removed = sorted(existing - new)
                if added:
                    metadata["reviewers_added"] = added
                if removed:
                    metadata["reviewers_removed"] = removed

        if not updates:
            return review

        updates["updated_at"] = datetime.now(timezone.utc)
        updated_review = await self.repository.update_review(review_id, updates)
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update review")

        await self.repository.add_review_event(
            review_id,
            ReviewEventType.UPDATED,
            author_id=actor_id,
            metadata=metadata or None,
        )
        return updated_review

    async def merge_review(self, review_id: str, reviewer_id: str, comment: Optional[str] = None) -> Tuple[Review, NoteVersion]:
        review = await self._require_review(review_id)
        if review.status == ReviewStatus.MERGED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review already merged")
        if review.created_by == reviewer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review creator cannot merge their own review")
        
        # Check if this is a special review without a draft_version_id (deletion or restore)
        if not review.draft_version_id:
            # Prefer explicit review.type if present, otherwise fallback to title prefix for compatibility
            rtype = (review.type or "").lower() if getattr(review, "type", None) else None
            if rtype is None or rtype == "":
                title = (review.title or "").lower()
                if title.startswith("delete:"):
                    rtype = "deletion"
                elif title.startswith("restore:"):
                    rtype = "restore"

            if rtype == "deletion":
                # This is a deletion request - mark the note as deleted
                await self.notes_service.delete_note(review.note_id, reviewer_id)
                event_metadata = {"note_id": review.note_id, "deletion": True}
            elif rtype == "restore":
                # This is a restore request - mark the note as restored
                await self.notes_service.restore_note(review.note_id, reviewer_id)
                event_metadata = {"note_id": review.note_id, "restore": True}
            else:
                # Unknown special review type
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported special review type")
            updated_review = await self.repository.update_review(
                review_id,
                {
                    "status": ReviewStatus.MERGED,
                    "merged_at": datetime.now(timezone.utc),
                    "merged_by": reviewer_id,
                    "merge_version_id": None,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            if not updated_review:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to merge deletion review")
            await self.repository.add_review_event(
                review_id,
                ReviewEventType.MERGED,
                author_id=reviewer_id,
                message=comment,
                metadata=event_metadata,
            )
            # Return a dummy version for deletion reviews
            base_version = await self.repository.get_version(review.base_version_id) if review.base_version_id else None
            if not base_version:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base version not found for deletion review")
            return updated_review, base_version
        
        # Normal merge flow for draft versions
        version = await self.notes_service.approve_version(review.draft_version_id, reviewer_id, review_comment=comment)
        updated_review = await self.repository.update_review(
            review_id,
            {
                "status": ReviewStatus.MERGED,
                "merged_at": datetime.now(timezone.utc),
                "merged_by": reviewer_id,
                "merge_version_id": version.id,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if not updated_review:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to merge review")
        await self.repository.add_review_event(
            review_id,
            ReviewEventType.MERGED,
            author_id=reviewer_id,
            message=comment,
            metadata={"note_id": review.note_id, "version_id": version.id},
        )
        return updated_review, version

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
        return await self.repository.list_reviews(
            status=status,
            created_by=created_by,
            reviewer_id=reviewer_id,
            involved_user=involved_user,
            note_id=note_id,
            limit=limit,
        )

    async def get_review_detail(self, review_id: str) -> Tuple[Review, NoteVersion, Optional[NoteVersion], List[ReviewEvent], Note]:
        review = await self._require_review(review_id)
        
        # Handle special reviews (empty draft_version_id). Use base version as the display version.
        if not review.draft_version_id:
            base_version = await self.repository.get_version(review.base_version_id) if review.base_version_id else None
            if not base_version:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base version missing for special review")
            note = await self.notes_service.get_note_metadata(review.note_id)
            events = await self.repository.list_review_events(review_id)
            return review, base_version, None, events, note
        
        version = await self.repository.get_version(review.draft_version_id)
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft version missing for review")
        base_version: Optional[NoteVersion] = None
        if review.base_version_id:
            base_version = await self.repository.get_version(review.base_version_id)
        note = await self.notes_service.get_note_metadata(review.note_id)
        events = await self.repository.list_review_events(review_id)
        return review, version, base_version, events, note

    async def get_active_review_for_version(self, version_id: str) -> Optional[Review]:
        review = await self.repository.get_review_by_version(version_id)
        if review and review.status in _ACTIVE_STATUSES:
            return review
        return None

    async def get_active_reviews_map(self, version_ids: Iterable[str]) -> Dict[str, Review]:
        mapping = await self.repository.get_reviews_by_version_ids(version_ids)
        return {
            version_id: review
            for version_id, review in mapping.items()
            if review.status in _ACTIVE_STATUSES
        }

    async def _require_review(self, review_id: str) -> Review:
        review = await self.repository.get_review(review_id)
        if not review:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
        return review
