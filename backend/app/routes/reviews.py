from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_notes_service, get_reviews_service
from ..models import Note, NoteState, NoteVersion, ReviewEvent, ReviewEventType, ReviewStatus
from ..services.notes import NotesService
from ..services.reviews import ReviewsService
from .notes import NoteResponse, _note_response_from_entities
from .review_models import ReviewInfoResponse

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _parse_statuses(param: Optional[str]) -> Optional[List[ReviewStatus]]:
    if not param:
        return None
    statuses: List[ReviewStatus] = []
    for raw in param.split(","):
        value = raw.strip()
        if not value:
            continue
        try:
            statuses.append(ReviewStatus(value))
        except ValueError as exc:  # pragma: no cover - validation path
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review status '{value}'") from exc
    return statuses or None


class CommentRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class DecisionRequest(BaseModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class ReviewUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    reviewer_ids: Optional[List[str]] = Field(default=None, min_length=1)


class ReviewMergeResponse(BaseModel):
    review: ReviewInfoResponse
    version: NoteResponse


class ReviewEventResponse(BaseModel):
    id: str
    event_type: ReviewEventType
    author_id: str
    message: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime

    @classmethod
    def from_entity(cls, event: ReviewEvent) -> "ReviewEventResponse":
        return cls(
            id=event.id or "",
            event_type=event.event_type,
            author_id=event.author_id,
            message=event.message,
            metadata=event.metadata,
            created_at=event.created_at,
        )


class ReviewSummaryResponse(BaseModel):
    review: ReviewInfoResponse
    draft_version: NoteResponse
    base_version: Optional[NoteResponse]


class ReviewDetailResponse(BaseModel):
    review: ReviewInfoResponse
    draft_version: NoteResponse
    base_version: Optional[NoteResponse]
    events: List[ReviewEventResponse]


@router.get("", response_model=List[ReviewSummaryResponse])
async def list_reviews(
    status: Optional[str] = Query(None, description="Comma separated list of statuses"),
    mine: bool = Query(False, description="Limit to reviews created by or assigned to the current user"),
    note_id: Optional[str] = Query(None, description="Filter by backing note id"),
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
    notes_service: NotesService = Depends(get_notes_service),
) -> List[ReviewSummaryResponse]:
    statuses = _parse_statuses(status)
    user_id = user.get("sub", user.get("user_id"))
    involved_user = user_id if mine else None
    reviews = await reviews_service.list_reviews(
        status=statuses,
        involved_user=involved_user,
        note_id=note_id,
    )
    summaries: List[ReviewSummaryResponse] = []
    for review in reviews:
        # Handle deletion reviews (empty draft_version_id)
        if not review.draft_version_id:
            # Use base version for deletion reviews
            version = await reviews_service.repository.get_version(review.base_version_id) if review.base_version_id else None
            if not version:
                continue
        else:
            version = await reviews_service.repository.get_version(review.draft_version_id)
            if not version:
                continue
        note: Note = await notes_service.get_note_metadata(review.note_id)
        draft_version = await _note_response_from_entities(
            note,
            version,
            service=notes_service,
            reviews_service=reviews_service,
        )
        base_version_response: Optional[NoteResponse] = None
        if review.base_version_id:
            base_version = await reviews_service.repository.get_version(review.base_version_id)
            if base_version:
                base_version_response = NoteResponse.from_entities(
                    note,
                    base_version,
                    has_draft=base_version.state == NoteState.DRAFT,
                    active_review=None,
                )
        summaries.append(
            ReviewSummaryResponse(
                review=ReviewInfoResponse.from_entity(review),
                draft_version=draft_version,
                base_version=base_version_response,
            )
        )
    return summaries


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def get_review_detail(
    review_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
    notes_service: NotesService = Depends(get_notes_service),
) -> ReviewDetailResponse:
    review, version, base_version, events, note = await reviews_service.get_review_detail(review_id)
    draft_version = await _note_response_from_entities(
        note,
        version,
        service=notes_service,
        reviews_service=reviews_service,
    )
    base_version_response: Optional[NoteResponse] = None
    if base_version:
        base_version_response = NoteResponse.from_entities(
            note,
            base_version,
            has_draft=base_version.state == NoteState.DRAFT,
            active_review=None,
        )
    return ReviewDetailResponse(
        review=ReviewInfoResponse.from_entity(review),
        draft_version=draft_version,
        base_version=base_version_response,
        events=[ReviewEventResponse.from_entity(event) for event in events],
    )


@router.post("/{review_id}/comment", response_model=ReviewEventResponse)
async def comment_on_review(
    review_id: str,
    payload: CommentRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewEventResponse:
    event = await reviews_service.comment_on_review(
        review_id,
        user.get("sub", user.get("user_id")),
        payload.message,
    )
    return ReviewEventResponse.from_entity(event)


@router.post("/{review_id}/approve", response_model=ReviewInfoResponse)
async def approve_review(
    review_id: str,
    payload: DecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await reviews_service.approve_review(
        review_id,
        reviewer_id=user.get("sub", user.get("user_id")),
        comment=payload.comment,
    )
    return ReviewInfoResponse.from_entity(review)


@router.patch("/{review_id}", response_model=ReviewInfoResponse)
async def update_review(
    review_id: str,
    payload: ReviewUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await reviews_service.update_review(
        review_id,
        user.get("sub", user.get("user_id")),
        title=payload.title,
        description=payload.description,
        reviewer_ids=payload.reviewer_ids,
    )
    return ReviewInfoResponse.from_entity(review)


@router.post("/{review_id}/request-changes", response_model=ReviewInfoResponse)
async def request_changes(
    review_id: str,
    payload: DecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await reviews_service.request_changes(
        review_id,
        reviewer_id=user.get("sub", user.get("user_id")),
        comment=payload.comment,
    )
    return ReviewInfoResponse.from_entity(review)


@router.post("/{review_id}/merge", response_model=ReviewMergeResponse)
async def merge_review(
    review_id: str,
    payload: DecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
    notes_service: NotesService = Depends(get_notes_service),
) -> ReviewMergeResponse:
    review, version = await reviews_service.merge_review(
        review_id,
        reviewer_id=user.get("sub", user.get("user_id")),
        comment=payload.comment,
    )
    note = await notes_service.get_note_metadata(review.note_id)
    version_response = await _note_response_from_entities(
        note,
        version,
        service=notes_service,
        reviews_service=reviews_service,
    )
    return ReviewMergeResponse(
        review=ReviewInfoResponse.from_entity(review),
        version=version_response,
    )


@router.post("/{review_id}/close", response_model=ReviewInfoResponse)
async def close_review(
    review_id: str,
    payload: DecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await reviews_service.close_review(
        review_id,
        actor_id=user.get("sub", user.get("user_id")),
        message=payload.comment,
    )
    return ReviewInfoResponse.from_entity(review)


@router.post("/{review_id}/reopen", response_model=ReviewInfoResponse)
async def reopen_review(
    review_id: str,
    payload: DecisionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await reviews_service.reopen_review(
        review_id,
        actor_id=user.get("sub", user.get("user_id")),
        message=payload.comment,
    )
    return ReviewInfoResponse.from_entity(review)
