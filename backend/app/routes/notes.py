from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..dependencies import get_notes_service, get_reviews_service
from ..models import Note, NoteState, NoteVersion, Review, ReviewStatus
from ..services.notes import NotesService
from ..services.reviews import ReviewsService
from .review_models import ReviewInfoResponse

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)


class NoteResponse(BaseModel):
    id: str
    title: str
    created_by: str
    committed_by: Optional[str]
    tags: List[str]
    state: NoteState
    version_id: str
    version_index: int
    content: str
    submitted_by: Optional[str]
    reviewed_by: Optional[str]
    review_comment: Optional[str]
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    created_at: datetime
    upvotes: int
    downvotes: int
    has_draft: bool = False
    active_review_id: Optional[str] = None
    active_review_status: Optional[ReviewStatus] = None

    @classmethod
    def from_entities(
        cls,
        note: Note,
        version: NoteVersion,
        *,
        has_draft: bool = False,
        active_review: Optional[Review] = None,
    ) -> "NoteResponse":
        return cls(
            id=note.id or version.note_id,
            title=version.title,
            created_by=note.created_by,
            committed_by=note.committed_by,
            deleted_at=note.deleted_at,
            deleted_by=note.deleted_by,
            tags=version.tags,
            state=version.state,
            version_id=version.id,
            version_index=version.version_index,
            content=version.content,
            submitted_by=version.submitted_by,
            reviewed_by=version.reviewed_by,
            review_comment=version.review_comment,
            created_at=version.created_at,
            upvotes=note.upvotes,
            downvotes=note.downvotes,
            has_draft=has_draft,
            active_review_id=active_review.id if active_review and active_review.id else None,
            active_review_status=active_review.status if active_review else None,
        )


class ReviewSubmissionResponse(BaseModel):
    version: NoteResponse
    review: ReviewInfoResponse


class DraftUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    state: Optional[NoteState] = None


class SubmitReviewRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    reviewer_ids: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    review_comment: Optional[str] = None

    def summary_message(self) -> Optional[str]:
        return self.summary if self.summary is not None else self.review_comment


class ApproveRequest(BaseModel):
    review_comment: Optional[str] = None
    review_id: Optional[str] = None


class SearchRequest(BaseModel):
    query: Optional[str] = None
    vector: Optional[List[float]] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=50)
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    sort_by: Optional[Literal["relevance", "author", "created_at", "committed_by"]] = None
    committed_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    states: List[NoteState] = Field(default_factory=list)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class VoteRequest(BaseModel):
    action: Literal["upvote", "downvote"]


class SearchResult(BaseModel):
    version: NoteResponse
    score: float


class SearchFacets(BaseModel):
    authors: List[str] = Field(default_factory=list)
    committers: List[str] = Field(default_factory=list)
    reviewers: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    items: List[SearchResult]
    page: int
    page_size: int
    total: int
    total_pages: int
    facets: SearchFacets


class NotesStatsResponse(BaseModel):
    total_notes: int
    total_versions: int
    approved_versions: int
    draft_versions: int
    needs_review_versions: int
    distinct_tags: int
    active_authors: int


async def _build_note_responses(
    versions: List[NoteVersion],
    service: NotesService,
    reviews_service: ReviewsService,
) -> List[NoteResponse]:
    if not versions:
        return []
    notes_map = await service.get_notes_by_ids([version.note_id for version in versions])
    drafts_map = await service.repository.get_drafts_by_note_ids([version.note_id for version in versions])
    active_reviews = await reviews_service.get_active_reviews_map(
        [version.id for version in versions if version.id]
    )
    responses: List[NoteResponse] = []
    for version in versions:
        note = notes_map.get(version.note_id)
        if note:
            has_draft = version.note_id in drafts_map and drafts_map[version.note_id].state == NoteState.DRAFT
            active_review = active_reviews.get(version.id) if version.id else None
            responses.append(
                NoteResponse.from_entities(
                    note,
                    version,
                    has_draft=has_draft,
                    active_review=active_review,
                )
            )
    return responses


async def _note_response_from_entities(
    note: Note,
    version: NoteVersion,
    *,
    service: NotesService,
    reviews_service: ReviewsService,
    has_draft: Optional[bool] = None,
) -> NoteResponse:
    resolved_has_draft = has_draft if has_draft is not None else await service.has_draft(note.id)
    active_review = await reviews_service.get_active_review_for_version(version.id)
    return NoteResponse.from_entities(
        note,
        version,
        has_draft=resolved_has_draft,
        active_review=active_review,
    )


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewSubmissionResponse:
    note, version = await service.create_note(
        author_id=user.get("sub", user.get("user_id")),
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
    )
    has_draft = await service.has_draft(note.id)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
        has_draft=has_draft,
    )


@router.patch("/versions/{version_id}", response_model=NoteResponse)
async def update_draft(
    version_id: str,
    payload: DraftUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    if payload.state is not None:
        # Handle state change separately
        version = await service.repository.get_version(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        version = await service.repository.update_version(version_id, {"state": payload.state})
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
    else:
        version = await service.update_draft(
            version_id,
            author_id=user.get("sub", user.get("user_id")),
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
    note = await service.get_note_metadata(version.note_id)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )


@router.delete("/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    version_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> Response:
    version = await service.repository.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    await service.repository.delete_version(version_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/versions/{version_id}/submit", response_model=ReviewSubmissionResponse)
async def submit_for_review(
    version_id: str,
    payload: SubmitReviewRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    version, review = await reviews_service.submit_version_for_review(
        version_id,
        user.get("sub", user.get("user_id")),
        title=payload.title,
        description=payload.description,
        reviewer_ids=payload.reviewer_ids or None,
        summary_comment=payload.summary_message(),
    )
    note = await service.get_note_metadata(version.note_id)
    version_response = await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )
    return ReviewSubmissionResponse(
        version=version_response,
        review=ReviewInfoResponse.from_entity(review),
    )


@router.post("/versions/{version_id}/approve", response_model=NoteResponse)
async def approve_version(
    version_id: str,
    payload: ApproveRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    reviewer_id = user.get("sub", user.get("user_id"))
    if payload.review_id:
        _, version = await reviews_service.merge_review(
            payload.review_id,
            reviewer_id,
            comment=payload.review_comment,
        )
    else:
        active_review = await reviews_service.get_active_review_for_version(version_id)
        if active_review:
            _, version = await reviews_service.merge_review(
                active_review.id or "",
                reviewer_id,
                comment=payload.review_comment,
            )
        else:
            version = await service.approve_version(
                version_id,
                reviewer_id=reviewer_id,
                review_comment=payload.review_comment,
            )
    note = await service.get_note_metadata(version.note_id)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )


@router.post("/{note_id}/draft", response_model=NoteResponse)
async def create_draft_from_current(
    note_id: str,
    payload: DraftUpdateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    if not payload.content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content is required for draft")
    version = await service.create_draft_from_current(
        note_id,
        author_id=user.get("sub", user.get("user_id")),
        updated_content=payload.content,
        title=payload.title,
        tags=payload.tags,
    )
    note = await service.get_note_metadata(version.note_id)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )


@router.delete("/{note_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def discard_draft(
    note_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> Response:
    await service.discard_draft(note_id, author_id=user.get("sub", user.get("user_id")))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{note_id}/history", response_model=List[NoteResponse])
async def get_history(
    note_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> List[NoteResponse]:
    versions = await service.note_history(note_id)
    note = await service.get_note_metadata(note_id)
    has_draft = await service.has_draft(note_id)
    active_reviews = await reviews_service.get_active_reviews_map([version.id for version in versions if version.id])
    responses: List[NoteResponse] = []
    for version in versions:
        version_has_draft = has_draft if version.state != NoteState.DRAFT else True
        responses.append(
            NoteResponse.from_entities(
                note,
                version,
                has_draft=version_has_draft,
                active_review=active_reviews.get(version.id) if version.id else None,
            )
        )
    return responses


@router.get("/drafts", response_model=List[NoteResponse])
async def list_my_drafts(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> List[NoteResponse]:
    versions = await service.list_user_drafts(user.get("sub", user.get("user_id")))
    return await _build_note_responses(versions, service, reviews_service)


@router.get("/review/queue", response_model=List[NoteResponse])
async def review_queue(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> List[NoteResponse]:
    versions = await service.list_review_queue()
    return await _build_note_responses(versions, service, reviews_service)


@router.post("/search", response_model=SearchResponse)
async def search_notes(
    payload: SearchRequest,
    include_drafts: bool = Query(False, alias="includeDrafts"),
    include_deleted: bool = Query(False, alias="includeDeleted"),
    legacy_allow_deleted: Optional[bool] = Query(None, alias="allowDeleted"),
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> SearchResponse:
    resolved_include_deleted = include_deleted or bool(legacy_allow_deleted)
    offset = (payload.page - 1) * payload.page_size
    results, total, facets = await service.search(
        keyword=payload.query,
        vector=payload.vector,
        sort_by=payload.sort_by,
        offset=offset,
        limit=payload.page_size,
        include_drafts=include_drafts,
        allow_deleted=resolved_include_deleted,
        author=payload.author,
        tags=payload.tags or None,
        committed_by=payload.committed_by,
        reviewed_by=payload.reviewed_by,
        states=payload.states or None,
        min_score=payload.min_score,
    )
    versions = [version for version, _ in results]
    notes_map = await service.get_notes_by_ids([version.note_id for version in versions])
    drafts_map = {}
    if include_drafts:
        drafts_map = await service.repository.get_drafts_by_note_ids([version.note_id for version in versions])
    active_reviews = await reviews_service.get_active_reviews_map(
        [version.id for version in versions if version.id]
    )
    output: List[SearchResult] = []
    for version, score in results:
        note = notes_map.get(version.note_id)
        if not note:
            continue
        has_draft = version.note_id in drafts_map and drafts_map[version.note_id].state == NoteState.DRAFT
        output.append(
            SearchResult(
                version=NoteResponse.from_entities(
                    note,
                    version,
                    has_draft=has_draft,
                    active_review=active_reviews.get(version.id) if version.id else None,
                ),
                score=score,
            )
        )
    total_pages = math.ceil(total / payload.page_size) if total else 0
    return SearchResponse(
        items=output,
        page=payload.page,
        page_size=payload.page_size,
        total=total,
        total_pages=total_pages,
        facets=SearchFacets(**facets),
    )


@router.get("/stats", response_model=NotesStatsResponse)
async def get_notes_stats(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> NotesStatsResponse:
    stats = await service.get_stats()
    return NotesStatsResponse(**stats)


class AuthorsResponse(BaseModel):
    authors: List[str]


@router.get("/authors", response_model=AuthorsResponse)
async def get_all_authors(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> AuthorsResponse:
    """Get list of all unique authors who have created notes."""
    authors = await service.get_all_authors()
    return AuthorsResponse(authors=sorted(authors))


class TagsResponse(BaseModel):
    tags: List[str]


@router.get("/tags", response_model=TagsResponse)
async def get_all_tags(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> TagsResponse:
    """Get list of all unique tags used in notes."""
    tags = await service.get_all_tags()
    return TagsResponse(tags=sorted(tags))


class CommittersResponse(BaseModel):
    committers: List[str]


@router.get("/committers", response_model=CommittersResponse)
async def get_all_committers(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> CommittersResponse:
    """Get list of all unique committers."""
    committers = await service.get_all_committers()
    return CommittersResponse(committers=committers)


class ReviewersResponse(BaseModel):
    reviewers: List[str]


@router.get("/reviewers", response_model=ReviewersResponse)
async def get_all_reviewers(
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
) -> ReviewersResponse:
    """Get list of all unique reviewers."""
    reviewers = await service.get_all_reviewers()
    return ReviewersResponse(reviewers=reviewers)


@router.post("/{note_id}/vote", response_model=NoteResponse)
async def vote_note(
    note_id: str,
    payload: VoteRequest,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    note, version = await service.vote_note(note_id, action=payload.action)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note_detail(
    note_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> NoteResponse:
    note, version = await service.get_note_detail(note_id)
    return await _note_response_from_entities(
        note,
        version,
        service=service,
        reviews_service=reviews_service,
    )


class DeleteNoteRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=2000, description="Reason for deletion")
    reviewer_ids: Optional[List[str]] = Field(default=None, description="Reviewers to approve deletion")


@router.delete("/{note_id}", response_model=ReviewInfoResponse)
async def delete_note(
    note_id: str,
    payload: DeleteNoteRequest = Body(...),
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await service.request_note_deletion(
        note_id,
        user.get("sub", user.get("user_id")),
        reason=payload.reason,
        reviewer_ids=payload.reviewer_ids,
    )
    return ReviewInfoResponse.from_entity(review)


@router.post("/{note_id}/restore", response_model=ReviewInfoResponse)
async def restore_note(
    note_id: str,
    payload: DeleteNoteRequest = Body(...),
    user: Dict[str, Any] = Depends(get_current_user),
    service: NotesService = Depends(get_notes_service),
    reviews_service: ReviewsService = Depends(get_reviews_service),
) -> ReviewInfoResponse:
    review = await service.request_note_restore(
        note_id,
        user.get("sub", user.get("user_id")),
        reason=payload.reason,
        reviewer_ids=payload.reviewer_ids,
    )
    return ReviewInfoResponse.from_entity(review)
