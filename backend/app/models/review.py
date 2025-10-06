from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ReviewStatus(str, Enum):
    OPEN = "open"
    CHANGES_REQUESTED = "changes_requested"
    MERGED = "merged"
    CLOSED = "closed"


class ReviewDecision(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"


class ReviewDecisionState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    decision: ReviewDecision
    comment: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("updated_at", when_used="json")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.isoformat()


class Review(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    note_id: str
    draft_version_id: str
    base_version_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    created_by: str
    reviewer_ids: List[str] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.OPEN
    review_decisions: Dict[str, ReviewDecisionState] = Field(default_factory=dict)
    merge_version_id: Optional[str] = None
    merged_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    # Optional explicit type for special reviews (deletion, restore, etc.)
    type: Optional[str] = None

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("updated_at", when_used="json")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("merged_at", when_used="json")
    def serialize_merged_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    @field_serializer("closed_at", when_used="json")
    def serialize_closed_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None


class ReviewEventType(str, Enum):
    SUBMITTED = "submitted"
    COMMENT = "comment"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    MERGED = "merged"
    CLOSED = "closed"
    REOPENED = "reopened"
    UPDATED = "updated"


class ReviewEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    review_id: str
    event_type: ReviewEventType
    author_id: str
    message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()
