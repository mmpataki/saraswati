from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId
try:  # pragma: no cover - optional dependency for tests
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
except ImportError:  # pragma: no cover - fall back to Any
    AsyncIOMotorClient = Any  # type: ignore[assignment]
    AsyncIOMotorCollection = Any  # type: ignore[assignment]

from ..config import SaraswatiSettings
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


def _oid(value: str | ObjectId) -> ObjectId:
    return value if isinstance(value, ObjectId) else ObjectId(value)


def _stringify_id(document: Dict[str, Any]) -> Dict[str, Any]:
    if document is None:
        return {}
    doc = document.copy()
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _serialize_review_decisions(decisions: Dict[str, ReviewDecisionState]) -> Dict[str, Dict[str, Any]]:
    serialized: Dict[str, Dict[str, Any]] = {}
    for user_id, state in decisions.items():
        serialized[user_id] = {
            "decision": state.decision.value if isinstance(state.decision, ReviewDecision) else str(state.decision),
            "comment": state.comment,
            "updated_at": state.updated_at,
        }
    return serialized


def _parse_review(doc: Dict[str, Any]) -> Optional[Review]:
    if not doc:
        return None
    normalized = _stringify_id(doc)
    status = normalized.get("status")
    if isinstance(status, str):
        normalized["status"] = ReviewStatus(status)
    decisions: Dict[str, Any] = normalized.get("review_decisions", {}) or {}
    parsed_decisions: Dict[str, ReviewDecisionState] = {}
    for user_id, payload in decisions.items():
        if isinstance(payload, ReviewDecisionState):
            parsed_decisions[user_id] = payload
            continue
        decision_value = payload.get("decision") if isinstance(payload, dict) else payload
        if decision_value is None:
            continue
        comment = payload.get("comment") if isinstance(payload, dict) else None
        updated_at = payload.get("updated_at") if isinstance(payload, dict) else None
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = datetime.now(timezone.utc)
        if not isinstance(updated_at, datetime):
            updated_at = datetime.now(timezone.utc)
        parsed_decisions[user_id] = ReviewDecisionState(
            decision=ReviewDecision(decision_value),
            comment=comment,
            updated_at=updated_at,
        )
    normalized["review_decisions"] = parsed_decisions
    for key in ("created_at", "updated_at", "merged_at", "closed_at"):
        value = normalized.get(key)
        if isinstance(value, str):
            try:
                normalized[key] = datetime.fromisoformat(value)
            except ValueError:
                normalized[key] = datetime.now(timezone.utc)
    return Review.parse_obj(normalized)


def _parse_review_event(doc: Dict[str, Any]) -> Optional[ReviewEvent]:
    if not doc:
        return None
    normalized = _stringify_id(doc)
    event_type = normalized.get("event_type")
    if isinstance(event_type, str):
        normalized["event_type"] = ReviewEventType(event_type)
    created_at = normalized.get("created_at")
    if isinstance(created_at, str):
        try:
            normalized["created_at"] = datetime.fromisoformat(created_at)
        except ValueError:
            normalized["created_at"] = datetime.now(timezone.utc)
    return ReviewEvent.parse_obj(normalized)


class NotesRepository:
    """Mongo-backed persistence for Saraswati notes."""

    def __init__(self, client: AsyncIOMotorClient, settings: SaraswatiSettings) -> None:
        if not settings.mongo:
            raise ValueError("Mongo settings must be provided to use the Mongo repository")
        self.client = client
        self.settings = settings
        mongo_cfg = settings.mongo
        db = client[mongo_cfg.database]
        self._notes = db[mongo_cfg.notes_collection]
        self._versions = db[mongo_cfg.versions_collection]
        self._reviews = db[mongo_cfg.reviews_collection]
        self._review_events = db[mongo_cfg.review_events_collection]

    async def create_note_with_version(
        self,
        title: str,
        content: str,
        tags: List[str],
        author_id: str,
        vector: Optional[List[float]] = None,
    ) -> Tuple[Note, NoteVersion]:
        now = datetime.now(timezone.utc)
        note_doc = {
            "title": title,
            "created_by": author_id,
            "tags": tags,
            "committed_by": None,
            "created_at": now,
            "upvotes": 0,
            "downvotes": 0,
        }
        note_result = await self._notes.insert_one(note_doc)
        note_id = str(note_result.inserted_id)

        version_doc = {
            "note_id": note_id,
            "version_index": 0,
            "title": title,
            "content": content,
            "tags": tags,
            "state": NoteState.DRAFT.value,
            "created_by": author_id,
            "vector": vector,
            "created_at": now,
        }
        version_result = await self._versions.insert_one(version_doc)
        version_id = str(version_result.inserted_id)

        await self._notes.update_one({"_id": _oid(note_id)}, {"$set": {"current_version_id": version_id}})

        note = Note.parse_obj(_stringify_id({"_id": note_id, **note_doc, "current_version_id": version_id}))
        version = NoteVersion.parse_obj(_stringify_id({"_id": version_id, **version_doc}))
        return note, version

    async def get_note(self, note_id: str) -> Optional[Note]:
        doc = await self._notes.find_one({"_id": _oid(note_id)})
        if not doc:
            return None
        return Note.parse_obj(_stringify_id(doc))

    async def get_version(self, version_id: str) -> Optional[NoteVersion]:
        doc = await self._versions.find_one({"_id": _oid(version_id)})
        if not doc:
            return None
        return NoteVersion.parse_obj(_stringify_id(doc))

    async def get_latest_version(self, note_id: str) -> Optional[NoteVersion]:
        cursor = self._versions.find({"note_id": note_id}).sort("version_index", -1).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            return None
        return NoteVersion.parse_obj(_stringify_id(docs[0]))

    async def list_note_versions(self, note_id: str) -> List[NoteVersion]:
        cursor = self._versions.find({"note_id": note_id}).sort("version_index", 1)
        versions = []
        async for doc in cursor:
            versions.append(NoteVersion.parse_obj(_stringify_id(doc)))
        return versions

    async def list_review_queue(self) -> List[NoteVersion]:
        cursor = self._versions.find({"state": {"$in": [NoteState.NEEDS_REVIEW.value]}}).sort("created_at", 1)
        items: List[NoteVersion] = []
        async for doc in cursor:
            items.append(NoteVersion.parse_obj(_stringify_id(doc)))
        return items

    async def update_version(self, version_id: str, updates: Dict[str, Any]) -> Optional[NoteVersion]:
        updates_to_apply = {**updates}
        if "state" in updates_to_apply and isinstance(updates_to_apply["state"], NoteState):
            updates_to_apply["state"] = updates_to_apply["state"].value
        result = await self._versions.find_one_and_update(
            {"_id": _oid(version_id)},
            {"$set": updates_to_apply},
            return_document=True,
        )
        if not result:
            return None
        return NoteVersion.parse_obj(_stringify_id(result))

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
        cursor = self._versions.find({"note_id": note_id}).sort("version_index", -1).limit(1)
        latest = await cursor.to_list(length=1)
        next_index = latest[0]["version_index"] + 1 if latest else 0
        now = datetime.now(timezone.utc)
        version_doc = {
            "note_id": note_id,
            "version_index": next_index,
            "title": title or base_version.title,
            "content": content,
            "tags": tags or base_version.tags,
            "state": NoteState.DRAFT.value,
            "created_by": author_id,
            "vector": vector,
            "created_at": now,
        }
        result = await self._versions.insert_one(version_doc)
        version_id = str(result.inserted_id)
        return NoteVersion.parse_obj(_stringify_id({"_id": version_id, **version_doc}))

    async def set_note_current_version(
        self,
        note_id: str,
        version_id: Optional[str],
        committed_by: Optional[str],
    ) -> None:
        update: Dict[str, Any] = {
            "current_version_id": version_id,
            "committed_by": committed_by,
        }
        await self._notes.update_one({"_id": _oid(note_id)}, {"$set": update})

    async def delete_note(self, note_id: str) -> None:
        await self._notes.delete_one({"_id": _oid(note_id)})
        await self._versions.delete_many({"note_id": note_id})

    async def mark_note_deleted(self, note_id: str, deleter_id: str) -> None:
        """Mark a note as deleted by setting deleted_at and deleted_by fields."""
        from datetime import datetime, timezone
        await self._notes.update_one(
            {"_id": _oid(note_id)},
            {"$set": {
                "deleted_at": datetime.now(timezone.utc),
                "deleted_by": deleter_id
            }}
        )

    async def mark_note_restored(self, note_id: str, restorer_id: str) -> None:
        """Clear deleted fields to restore a note."""
        await self._notes.update_one(
            {"_id": _oid(note_id)},
            {"$unset": {"deleted_at": "", "deleted_by": ""}}
        )

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        unique_ids = {note_id for note_id in note_ids if note_id}
        object_ids: List[ObjectId] = []
        for value in unique_ids:
            try:
                object_ids.append(_oid(value))
            except InvalidId:
                continue
        if not object_ids:
            return {}
        cursor = self._notes.find({"_id": {"$in": object_ids}})
        results: Dict[str, Note] = {}
        async for doc in cursor:
            note = Note.parse_obj(_stringify_id(doc))
            if note.id:
                results[note.id] = note
        return results

    async def list_notes(self, *, skip: int = 0, limit: int = 50) -> List[Note]:
        cursor = self._notes.find().sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [Note.parse_obj(_stringify_id(doc)) for doc in docs]

    async def count_notes(self) -> int:
        return await self._notes.count_documents({})

    async def update_vote_counts(
        self,
        note_id: str,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
    ) -> Optional[Note]:
        note = await self.get_note(note_id)
        if not note:
            return None
        new_up = max(0, note.upvotes + up_delta)
        new_down = max(0, note.downvotes + down_delta)
        await self._notes.update_one(
            {"_id": _oid(note_id)},
            {
                "$set": {
                    "upvotes": new_up,
                    "downvotes": new_down,
                }
            },
        )
        note.upvotes = new_up
        note.downvotes = new_down
        return note

    async def keyword_search(self, query: str, limit: int = 10) -> List[NoteVersion]:
        regex = {"$regex": query, "$options": "i"}
        cursor = self._versions.find(
            {
                "state": {"$in": [state.value for state in NoteState]},
                "$or": [{"title": regex}, {"content": regex}],
            }
        )
        docs = await cursor.to_list(length=limit * 3)

        priority = {
            NoteState.APPROVED.value: 0,
            NoteState.NEEDS_REVIEW.value: 1,
            NoteState.DRAFT.value: 2,
        }

        docs.sort(key=lambda doc: priority.get(doc.get("state"), 99))
        items: List[NoteVersion] = [NoteVersion.parse_obj(_stringify_id(doc)) for doc in docs[:limit]]
        return items

    async def list_user_drafts(self, author_id: str, limit: int = 50) -> List[NoteVersion]:
        cursor = (
            self._versions.find({"state": NoteState.DRAFT.value, "created_by": author_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [NoteVersion.parse_obj(_stringify_id(doc)) for doc in docs]

    async def vector_search(self, vector: List[float], limit: int = 5) -> List[Tuple[NoteVersion, float]]:
        cursor = self._versions.find({"state": NoteState.APPROVED.value, "vector": {"$exists": True}})
        scored: List[Tuple[NoteVersion, float]] = []
        async for doc in cursor:
            version = NoteVersion.parse_obj(_stringify_id(doc))
            if version.vector:
                score = _cosine_similarity(vector, version.vector)
                scored.append((version, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    async def get_drafts_by_note_ids(self, note_ids: Iterable[str]) -> Dict[str, NoteVersion]:
        unique_ids = {note_id for note_id in note_ids if note_id}
        if not unique_ids:
            return {}
        cursor = self._versions.find({
            "note_id": {"$in": list(unique_ids)},
            "state": NoteState.DRAFT.value,
        })
        drafts: Dict[str, NoteVersion] = {}
        async for doc in cursor:
            version = NoteVersion.parse_obj(_stringify_id(doc))
            existing = drafts.get(version.note_id)
            if not existing or existing.version_index < version.version_index:
                drafts[version.note_id] = version
        return drafts

    async def delete_version(self, version_id: str) -> None:
        await self._versions.delete_one({"_id": _oid(version_id)})

    async def get_stats(self) -> Dict[str, int]:
        total_notes = await self._notes.count_documents({})
        total_versions = await self._versions.count_documents({})
        approved_versions = await self._versions.count_documents({"state": NoteState.APPROVED.value})
        draft_versions = await self._versions.count_documents({"state": NoteState.DRAFT.value})
        needs_review_versions = await self._versions.count_documents({"state": NoteState.NEEDS_REVIEW.value})
        tags = await self._versions.distinct("tags")
        distinct_tags = len({tag for tag in tags if isinstance(tag, str)})
        active_authors = len({author for author in await self._versions.distinct("created_by") if isinstance(author, str)})

        return {
            "total_notes": total_notes,
            "total_versions": total_versions,
            "approved_versions": approved_versions,
            "draft_versions": draft_versions,
            "needs_review_versions": needs_review_versions,
            "distinct_tags": distinct_tags,
            "active_authors": active_authors,
        }

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
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "note_id": note_id,
            "draft_version_id": draft_version_id,
            "base_version_id": base_version_id,
            "title": title,
            "description": description,
            "created_by": created_by,
            "reviewer_ids": reviewer_ids or [],
            "type": review_type,
            "status": ReviewStatus.OPEN.value,
            "review_decisions": {},
            "merge_version_id": None,
            "merged_by": None,
            "created_at": now,
            "updated_at": now,
            "merged_at": None,
            "closed_at": None,
        }
        result = await self._reviews.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return _parse_review(doc)

    async def update_review(self, review_id: str, updates: Dict[str, object]) -> Optional[Review]:
        updates_to_apply: Dict[str, Any] = {}
        for key, value in updates.items():
            if isinstance(value, ReviewStatus):
                updates_to_apply[key] = value.value
            elif key == "review_decisions" and isinstance(value, dict):
                normalized: Dict[str, Any] = {}
                for user_id, state in value.items():
                    if isinstance(state, ReviewDecisionState):
                        normalized[user_id] = {
                            "decision": state.decision.value,
                            "comment": state.comment,
                            "updated_at": state.updated_at,
                        }
                    elif isinstance(state, dict):
                        normalized[user_id] = {
                            "decision": ReviewDecision(state.get("decision")).value,
                            "comment": state.get("comment"),
                            "updated_at": state.get("updated_at"),
                        }
                updates_to_apply[key] = normalized
            elif isinstance(value, ReviewDecisionState):
                updates_to_apply[key] = {
                    "decision": value.decision.value,
                    "comment": value.comment,
                    "updated_at": value.updated_at,
                }
            else:
                updates_to_apply[key] = value

        result = await self._reviews.find_one_and_update(
            {"_id": _oid(review_id)},
            {"$set": updates_to_apply},
            return_document=True,
        )
        if not result:
            return None
        return _parse_review(result)

    async def get_review(self, review_id: str) -> Optional[Review]:
        doc = await self._reviews.find_one({"_id": _oid(review_id)})
        return _parse_review(doc)

    async def get_review_by_version(self, draft_version_id: str) -> Optional[Review]:
        doc = await self._reviews.find_one({"draft_version_id": draft_version_id})
        return _parse_review(doc)

    async def get_reviews_by_version_ids(self, version_ids: Iterable[str]) -> Dict[str, Review]:
        version_list = [version_id for version_id in set(version_ids) if version_id]
        if not version_list:
            return {}
        cursor = self._reviews.find({"draft_version_id": {"$in": version_list}})
        results: Dict[str, Review] = {}
        async for doc in cursor:
            review = _parse_review(doc)
            if review:
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
        base_query: Dict[str, Any] = {}
        if status:
            base_query["status"] = {"$in": [entry.value for entry in status]}
        if created_by:
            base_query["created_by"] = created_by
        if reviewer_id:
            base_query["reviewer_ids"] = {"$in": [reviewer_id]}
        if note_id:
            base_query["note_id"] = note_id

        query: Dict[str, Any]
        if involved_user:
            involvement_filter = {"$or": [{"created_by": involved_user}, {"reviewer_ids": involved_user}]}
            if base_query:
                query = {"$and": [base_query, involvement_filter]}
            else:
                query = involvement_filter
        else:
            query = base_query

        cursor = (
            self._reviews.find(query)
            .sort("updated_at", -1)
            .limit(limit)
        )
        items: List[Review] = []
        async for doc in cursor:
            review = _parse_review(doc)
            if review:
                items.append(review)
        return items

    async def add_review_event(
        self,
        review_id: str,
        event_type: ReviewEventType,
        *,
        author_id: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ReviewEvent:
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "review_id": review_id,
            "event_type": event_type.value,
            "author_id": author_id,
            "message": message,
            "metadata": metadata or {},
            "created_at": now,
        }
        result = await self._review_events.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return _parse_review_event(doc)

    async def list_review_events(self, review_id: str, limit: int = 200) -> List[ReviewEvent]:
        cursor = (
            self._review_events.find({"review_id": review_id})
            .sort("created_at", 1)
            .limit(limit)
        )
        events: List[ReviewEvent] = []
        async for doc in cursor:
            event = _parse_review_event(doc)
            if event:
                events.append(event)
        return events
