from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from ..models import Review, ReviewDecision, ReviewDecisionState, ReviewStatus


class ReviewDecisionResponse(BaseModel):
    user_id: str
    decision: ReviewDecision
    comment: Optional[str]
    updated_at: datetime

    @classmethod
    def from_state(cls, user_id: str, state: ReviewDecisionState) -> "ReviewDecisionResponse":
        return cls(user_id=user_id, decision=state.decision, comment=state.comment, updated_at=state.updated_at)


class ReviewInfoResponse(BaseModel):
    id: str
    note_id: str
    draft_version_id: str
    base_version_id: Optional[str]
    title: str
    description: Optional[str]
    created_by: str
    reviewer_ids: List[str]
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime]
    merged_by: Optional[str]
    closed_at: Optional[datetime]
    merge_version_id: Optional[str]
    type: Optional[str]
    approvals_count: int
    change_requests_count: int
    decisions: List[ReviewDecisionResponse]

    @classmethod
    def from_entity(cls, review: Review) -> "ReviewInfoResponse":
        decisions = [ReviewDecisionResponse.from_state(user_id, state) for user_id, state in review.review_decisions.items()]
        approvals = sum(1 for decision in decisions if decision.decision == ReviewDecision.APPROVED)
        change_requests = sum(1 for decision in decisions if decision.decision == ReviewDecision.CHANGES_REQUESTED)
        return cls(
            id=review.id or "",
            note_id=review.note_id,
            draft_version_id=review.draft_version_id,
            base_version_id=review.base_version_id,
            title=review.title,
            description=review.description,
            created_by=review.created_by,
            reviewer_ids=review.reviewer_ids,
            status=review.status,
            created_at=review.created_at,
            updated_at=review.updated_at,
            merged_at=review.merged_at,
            merged_by=review.merged_by,
            closed_at=review.closed_at,
            merge_version_id=review.merge_version_id,
            type=getattr(review, "type", None),
            approvals_count=approvals,
            change_requests_count=change_requests,
            decisions=decisions,
        )
