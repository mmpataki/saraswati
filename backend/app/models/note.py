from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_serializer


class NoteState(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"


class NoteVersion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    note_id: str
    version_index: int = Field(..., ge=0)
    title: str
    content: str
    tags: List[str]
    state: NoteState = NoteState.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    submitted_by: Optional[str] = None
    committed_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_comment: Optional[str] = None
    vector: Optional[List[float]] = None

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()


class Note(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str
    committed_by: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    current_version_id: Optional[str] = None
    upvotes: int = Field(0, ge=0)
    downvotes: int = Field(0, ge=0)
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None

    @field_serializer("created_at", when_used="json")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer("deleted_at", when_used="json")
    def serialize_deleted_at(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
