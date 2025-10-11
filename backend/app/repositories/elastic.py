from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from elasticsearch import AsyncElasticsearch
from elasticsearch import NotFoundError

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
from .interface import NotesRepositoryProtocol

class ElasticsearchNotesRepository(NotesRepositoryProtocol):
    """Elasticsearch-backed notes persistence layer."""

    def __init__(self, client: AsyncElasticsearch, settings: SaraswatiSettings) -> None:
        if not settings.elasticsearch:
            raise ValueError("Elasticsearch settings are required for the elastic store backend")
        self.client = client
        self._settings = settings
        self._cfg = settings.elasticsearch
        self._notes_index = self._cfg.notes_index
        self._versions_index = self._cfg.versions_index
        self._reviews_index = self._cfg.reviews_index
        self._review_events_index = self._cfg.review_events_index
        self._indices_ready = False
        self._indices_lock = asyncio.Lock()

    async def _ensure_indices(self) -> None:
        if self._indices_ready:
            return
        async with self._indices_lock:
            if self._indices_ready:
                return
            # Create indices with explicit mappings so fields like `created_at` exist
            # and can be used for sorting. Avoid dynamic mapping surprises.
            notes_mapping = {
                "mappings": {
                    "properties": {
                        "created_at": {"type": "date"},
                        "created_by": {"type": "keyword"},
                        "committed_by": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "current_version_id": {"type": "keyword"},
                        "upvotes": {"type": "integer"},
                        "downvotes": {"type": "integer"},
                    }
                }
            }

            versions_mapping = {
                "mappings": {
                    "properties": {
                        "created_at": {"type": "date"},
                        "note_id": {"type": "keyword"},
                        "created_by": {"type": "keyword"},
                        "submitted_by": {"type": "keyword"},
                        "committed_by": {"type": "keyword"},
                        "reviewed_by": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "version_index": {"type": "integer"},
                        "tags": {"type": "keyword"},
                    }
                }
            }

            reviews_mapping = {
                "mappings": {
                    "properties": {
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "merged_at": {"type": "date"},
                        "closed_at": {"type": "date"},
                        "status": {"type": "keyword"},
                        "note_id": {"type": "keyword"},
                        "draft_version_id": {"type": "keyword"},
                        "base_version_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "description": {"type": "text"},
                        "created_by": {"type": "keyword"},
                        "reviewer_ids": {"type": "keyword"},
                        "merge_version_id": {"type": "keyword"},
                        "merged_by": {"type": "keyword"},
                        "review_decisions": {"type": "object", "enabled": True},
                    }
                }
            }

            review_events_mapping = {
                "mappings": {
                    "properties": {
                        "created_at": {"type": "date"},
                        "event_type": {"type": "keyword"},
                        "author_id": {"type": "keyword"},
                        "review_id": {"type": "keyword"},
                        "message": {"type": "text"},
                        "metadata": {"type": "object", "enabled": True},
                    }
                }
            }

            exists = await self.client.indices.exists(index=self._notes_index)
            if not exists:
                await self.client.indices.create(index=self._notes_index, body=notes_mapping)

            exists = await self.client.indices.exists(index=self._versions_index)
            if not exists:
                await self.client.indices.create(index=self._versions_index, body=versions_mapping)

            exists = await self.client.indices.exists(index=self._reviews_index)
            if not exists:
                await self.client.indices.create(index=self._reviews_index, body=reviews_mapping)

            exists = await self.client.indices.exists(index=self._review_events_index)
            if not exists:
                await self.client.indices.create(index=self._review_events_index, body=review_events_mapping)
            self._indices_ready = True

    @staticmethod
    def _note_to_document(note: Note) -> Dict[str, Any]:
        doc = json.loads(note.model_dump_json(by_alias=True))
        # Elasticsearch treats `_id` as a metadata field; don't include it inside the
        # document body when calling index(). The API accepts the id separately.
        doc.pop("_id", None)
        return doc

    @staticmethod
    def _version_to_document(version: NoteVersion) -> Dict[str, Any]:
        doc = json.loads(version.model_dump_json(by_alias=True))
        doc.pop("_id", None)
        return doc

    @staticmethod
    def _review_to_document(review: Review) -> Dict[str, Any]:
        doc = json.loads(review.model_dump_json(by_alias=True))
        doc.pop("_id", None)
        doc["status"] = review.status.value if isinstance(review.status, ReviewStatus) else doc.get("status")
        serialized_decisions: Dict[str, Any] = {}
        for user_id, state in review.review_decisions.items():
            serialized_decisions[user_id] = {
                "decision": state.decision.value if isinstance(state.decision, ReviewDecision) else state.decision,
                "comment": state.comment,
                "updated_at": state.updated_at.isoformat(),
            }
        doc["review_decisions"] = serialized_decisions
        return doc

    @staticmethod
    def _review_event_to_document(event: ReviewEvent) -> Dict[str, Any]:
        doc = json.loads(event.model_dump_json(by_alias=True))
        doc.pop("_id", None)
        doc["event_type"] = event.event_type.value if isinstance(event.event_type, ReviewEventType) else doc.get("event_type")
        return doc

    @staticmethod
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

    @staticmethod
    def _hit_to_note(hit: Dict[str, Any]) -> Note:
        source = dict(hit.get("_source", {}))
        source["_id"] = hit.get("_id")
        return Note.parse_obj(source)

    @staticmethod
    def _hit_to_version(hit: Dict[str, Any]) -> NoteVersion:
        source = dict(hit.get("_source", {}))
        source["_id"] = hit.get("_id")
        return NoteVersion.parse_obj(source)

    @staticmethod
    def _hit_to_review(hit: Dict[str, Any]) -> Review:
        source = dict(hit.get("_source", {}))
        source["_id"] = hit.get("_id")
        decisions = source.get("review_decisions", {}) or {}
        normalized: Dict[str, ReviewDecisionState] = {}
        for user_id, payload in decisions.items():
            decision_value = payload.get("decision") if isinstance(payload, dict) else payload
            comment = payload.get("comment") if isinstance(payload, dict) else None
            updated_at_raw = payload.get("updated_at") if isinstance(payload, dict) else None
            if isinstance(updated_at_raw, str):
                try:
                    updated_at = datetime.fromisoformat(updated_at_raw)
                except ValueError:
                    updated_at = datetime.now(timezone.utc)
            elif isinstance(updated_at_raw, datetime):
                updated_at = updated_at_raw
            else:
                updated_at = datetime.now(timezone.utc)
            normalized[user_id] = ReviewDecisionState(
                decision=ReviewDecision(decision_value),
                comment=comment,
                updated_at=updated_at,
            )
        source["review_decisions"] = normalized
        status = source.get("status")
        if isinstance(status, str):
            source["status"] = ReviewStatus(status)
        return Review.parse_obj(source)

    @staticmethod
    def _hit_to_review_event(hit: Dict[str, Any]) -> ReviewEvent:
        source = dict(hit.get("_source", {}))
        source["_id"] = hit.get("_id")
        event_type = source.get("event_type")
        if isinstance(event_type, str):
            source["event_type"] = ReviewEventType(event_type)
        created_at = source.get("created_at")
        if isinstance(created_at, str):
            try:
                source["created_at"] = datetime.fromisoformat(created_at)
            except ValueError:
                source["created_at"] = datetime.now(timezone.utc)
        return ReviewEvent.parse_obj(source)

    async def create_note_with_version(
        self,
        title: str,
        content: str,
        tags: List[str],
        author_id: str,
        vector: Optional[List[float]] = None,
    ) -> Tuple[Note, NoteVersion]:
        await self._ensure_indices()
        note_id = uuid4().hex
        version_id = uuid4().hex

        note = Note(
            _id=note_id,
            title=title,
            created_by=author_id,
            tags=tags,
            current_version_id=version_id,
            upvotes=0,
            downvotes=0,
        )
        version = NoteVersion(
            _id=version_id,
            note_id=note_id,
            version_index=0,
            title=title,
            content=content,
            tags=tags,
            created_by=author_id,
            state=NoteState.DRAFT,
            vector=vector,
        )

        await self.client.index(
            index=self._notes_index,
            id=note_id,
            document=self._note_to_document(note),
            refresh="wait_for",
        )
        await self.client.index(
            index=self._versions_index,
            id=version_id,
            document=self._version_to_document(version),
            refresh="wait_for",
        )
        return note, version

    async def get_note(self, note_id: str) -> Optional[Note]:
        await self._ensure_indices()
        try:
            doc = await self.client.get(index=self._notes_index, id=note_id)
        except NotFoundError:
            return None
        return self._hit_to_note(doc)

    async def get_version(self, version_id: str) -> Optional[NoteVersion]:
        await self._ensure_indices()
        try:
            doc = await self.client.get(index=self._versions_index, id=version_id)
        except NotFoundError:
            return None
        return self._hit_to_version(doc)

    async def get_latest_version(self, note_id: str) -> Optional[NoteVersion]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._versions_index,
            size=1,
            query={"term": {"note_id": note_id}},
            sort=[{"version_index": {"order": "desc"}}],
        )
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return None
        return self._hit_to_version(hits[0])

    async def list_note_versions(self, note_id: str) -> List[NoteVersion]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._versions_index,
            size=500,
            query={"term": {"note_id": note_id}},
            sort=[{"version_index": {"order": "asc"}}],
        )
        return [self._hit_to_version(hit) for hit in response.get("hits", {}).get("hits", [])]

    async def list_review_queue(self) -> List[NoteVersion]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._versions_index,
            size=500,
            query={"term": {"state": NoteState.NEEDS_REVIEW.value}},
            sort=[{"created_at": {"order": "asc"}}],
        )
        return [self._hit_to_version(hit) for hit in response.get("hits", {}).get("hits", [])]

    async def update_version(self, version_id: str, updates: Dict[str, Any]) -> Optional[NoteVersion]:
        await self._ensure_indices()
        payload: Dict[str, Any] = {}
        for key, value in updates.items():
            if isinstance(value, NoteState):
                payload[key] = value.value
            else:
                payload[key] = value
        if not payload:
            return await self.get_version(version_id)
        try:
            await self.client.update(
                index=self._versions_index,
                id=version_id,
                doc=payload,
                refresh="wait_for",
            )
        except NotFoundError:
            return None
        return await self.get_version(version_id)

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
        await self._ensure_indices()
        response = await self.client.search(
            index=self._versions_index,
            size=1,
            query={"term": {"note_id": note_id}},
            sort=[{"version_index": {"order": "desc"}}],
        )
        hits = response.get("hits", {}).get("hits", [])
        latest_index = base_version.version_index
        if hits:
            latest = self._hit_to_version(hits[0])
            latest_index = max(latest.version_index, base_version.version_index)
        next_index = latest_index + 1

        version_id = uuid4().hex
        version = NoteVersion(
            _id=version_id,
            note_id=note_id,
            version_index=next_index,
            title=title or base_version.title,
            content=content,
            tags=tags or base_version.tags,
            created_by=author_id,
            state=NoteState.DRAFT,
            vector=vector,
        )
        await self.client.index(
            index=self._versions_index,
            id=version_id,
            document=self._version_to_document(version),
            refresh="wait_for",
        )
        return version

    async def set_note_current_version(
        self,
        note_id: str,
        version_id: Optional[str],
        committed_by: Optional[str],
    ) -> None:
        await self._ensure_indices()
        try:
            await self.client.update(
                index=self._notes_index,
                id=note_id,
                doc={
                    "current_version_id": version_id,
                    "committed_by": committed_by,
                },
                refresh="wait_for",
            )
        except NotFoundError:
            return

    async def delete_note(self, note_id: str) -> None:
        await self._ensure_indices()
        await self.client.delete(index=self._notes_index, id=note_id, ignore=[404], refresh="wait_for")
        await self.client.delete_by_query(
            index=self._versions_index,
            query={"term": {"note_id": note_id}},
            refresh=True,
        )

    async def mark_note_deleted(self, note_id: str, deleter_id: str) -> None:
        """Mark a note as deleted by setting deleted_at and deleted_by fields."""
        from datetime import datetime, timezone
        await self._ensure_indices()
        await self.client.update(
            index=self._notes_index,
            id=note_id,
            body={
                "doc": {
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_by": deleter_id
                }
            },
            refresh="wait_for",
        )

    async def mark_note_restored(self, note_id: str, restorer_id: str) -> None:
        """Clear deleted fields in elastic document to restore a note."""
        await self._ensure_indices()
        await self.client.update(
            index=self._notes_index,
            id=note_id,
            body={
                "doc": {"deleted_at": None, "deleted_by": None}
            },
            refresh="wait_for",
        )

    async def get_notes_by_ids(self, note_ids: Iterable[str]) -> Dict[str, Note]:
        await self._ensure_indices()
        ids = [note_id for note_id in note_ids if note_id]
        if not ids:
            return {}
        response = await self.client.mget(index=self._notes_index, ids=ids)
        results: Dict[str, Note] = {}
        for doc in response.get("docs", []):
            if not doc.get("found"):
                continue
            source = dict(doc.get("_source", {}))
            source["_id"] = doc.get("_id")
            note = Note.parse_obj(source)
            if note.id:
                results[note.id] = note
        return results

    async def update_vote_counts(
        self,
        note_id: str,
        *,
        up_delta: int = 0,
        down_delta: int = 0,
    ) -> Optional[Note]:
        await self._ensure_indices()
        script = {
            "source": (
                "ctx._source.upvotes = Math.max(0, (ctx._source.upvotes ?: 0) + params.up_delta);"
                "ctx._source.downvotes = Math.max(0, (ctx._source.downvotes ?: 0) + params.down_delta);"
            ),
            "params": {"up_delta": up_delta, "down_delta": down_delta},
        }
        try:
            await self.client.update(
                index=self._notes_index,
                id=note_id,
                script=script,
                refresh="wait_for",
            )
        except NotFoundError:
            return None
        return await self.get_note(note_id)

    async def hybrid_search(
        self,
        *,
        keyword: Optional[str] = None,
        vector: Optional[List[float]] = None,
        limit: int = 50,
        include_drafts: bool = False,
        allow_deleted: bool = False,
        states: Optional[List[NoteState]] = None,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None,
        committed_by: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        sort_by: Optional[str] = None,
    ) -> Tuple[List[Tuple[NoteVersion, float]], int, Dict[str, List[str]]]:
        await self._ensure_indices()
        
        resolved_states = [NoteState.APPROVED.value]
        if include_drafts:
            resolved_states.append(NoteState.NEEDS_REVIEW.value)
        if allow_deleted:
            resolved_states.append(NoteState.DELETED.value)

        filter_clauses: List[Dict[str, Any]] = [
            {"terms": {"state": resolved_states}},
        ]
        if author:
            filter_clauses.append({"term": {"created_by": author}})
        if committed_by:
            filter_clauses.append({"term": {"committed_by": committed_by}})
        if reviewed_by:
            filter_clauses.append({"term": {"reviewed_by": reviewed_by}})
        if tags:
            filter_clauses.append(
                {
                    "terms_set": {
                        "tags": {
                            "terms": list(tags),
                            "minimum_should_match_script": {"source": "params.num_terms"},
                        }
                    }
                }
            )

        bool_query: Dict[str, Any] = {"filter": filter_clauses}
        normalized_keyword = (keyword or "").strip()
        if normalized_keyword and normalized_keyword != "*":
            bool_query.setdefault("must", []).append(
                {
                    "multi_match": {
                        "query": normalized_keyword,
                        "fields": ["title^2", "content", "tags"],
                    }
                }
            )

        resolved_sort = (sort_by or "relevance").lower()
        sort_clauses: List[Dict[str, Any]] = []
        key_map = {"author": "created_by", "created_at": "created_at", "committed_by": "committed_by"}
        if resolved_sort != "relevance":
            sort_clauses = [{key_map[resolved_sort]: {"order": "asc"}}]

        search_kwargs: Dict[str, Any] = {
            "index": self._versions_index,
            "size": max(limit, 10),
            "track_total_hits": True,
            "aggs": {
                "authors": {"terms": {"field": "created_by", "size": 100}},
                "committers": {"terms": {"field": "committed_by", "size": 100}},
                "reviewers": {"terms": {"field": "reviewed_by", "size": 100}},
                "tags": {"terms": {"field": "tags", "size": 200}},
            },
        }

        if sort_clauses:
            search_kwargs["sort"] = sort_clauses

        if bool_query.get("filter") or bool_query.get("must"):
            search_kwargs["query"] = {"bool": bool_query}
        else:
            search_kwargs["query"] = {"match_all": {}}

        if vector:
            search_kwargs["knn"] = {
                "field": "vector",
                "query_vector": vector,
                "k": max(limit * 2, 20),
                "num_candidates": max(limit * 10, 200),
            }
            if filter_clauses:
                search_kwargs["knn"]["filter"] = {"bool": {"filter": filter_clauses}}

        response = await self.client.search(**search_kwargs)
        hits = response.get("hits", {})
        total = int(hits.get("total", {}).get("value", len(hits.get("hits", []))))
        results: List[Tuple[NoteVersion, float]] = []
        for hit in hits.get("hits", []):
            version = self._hit_to_version(hit)
            score = float(hit.get("_score", 0.0) or 0.0)
            results.append((version, score))

        aggregations = response.get("aggregations", {}) or {}

        def _extract(name: str) -> List[str]:
            buckets = aggregations.get(name, {}).get("buckets", [])
            values = [bucket.get("key") for bucket in buckets if isinstance(bucket.get("key"), str) and bucket.get("key")]
            return sorted(set(values))

        facets = {
            "authors": _extract("authors"),
            "committers": _extract("committers"),
            "reviewers": _extract("reviewers"),
            "tags": _extract("tags"),
        }
        return results, total, facets

    async def get_drafts_by_note_ids(self, note_ids: Iterable[str]) -> Dict[str, NoteVersion]:
        await self._ensure_indices()
        ids = [note_id for note_id in note_ids if note_id]
        if not ids:
            return {}
        response = await self.client.search(
            index=self._versions_index,
            size=len(ids) * 10,
            query={
                "bool": {
                    "must": [
                        {"terms": {"note_id": ids}},
                        {"term": {"state": NoteState.DRAFT.value}},
                    ]
                }
            },
            sort=[{"version_index": {"order": "desc"}}],
        )
        drafts: Dict[str, NoteVersion] = {}
        for hit in response.get("hits", {}).get("hits", []):
            version = self._hit_to_version(hit)
            existing = drafts.get(version.note_id)
            if not existing or existing.version_index < version.version_index:
                drafts[version.note_id] = version
        return drafts

    async def delete_version(self, version_id: str) -> None:
        await self._ensure_indices()
        await self.client.delete(index=self._versions_index, id=version_id, ignore=[404], refresh="wait_for")

    async def list_user_drafts(self, author_id: str, limit: int = 50) -> List[NoteVersion]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._versions_index,
            size=limit,
            query={
                "bool": {
                    "must": [
                        {"term": {"state": NoteState.DRAFT.value}},
                        {"term": {"created_by": author_id}},
                    ]
                }
            },
            sort=[{"created_at": {"order": "desc"}}],
        )
        return [self._hit_to_version(hit) for hit in response.get("hits", {}).get("hits", [])]

    async def list_notes(self, *, skip: int = 0, limit: int = 50) -> List[Note]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._notes_index,
            size=limit,
            from_=skip,
            sort=[{"created_at": {"order": "desc"}}],
        )
        return [self._hit_to_note(hit) for hit in response.get("hits", {}).get("hits", [])]

    async def count_notes(self) -> int:
        await self._ensure_indices()
        response = await self.client.count(index=self._notes_index)
        return int(response.get("count", 0))

    async def get_stats(self) -> Dict[str, int]:
        await self._ensure_indices()
        total_notes = int((await self.client.count(index=self._notes_index)).get("count", 0))
        total_versions = int((await self.client.count(index=self._versions_index)).get("count", 0))
        approved_versions = int(
            (await self.client.count(index=self._versions_index, query={"term": {"state": NoteState.APPROVED.value}})).get(
                "count", 0
            )
        )
        draft_versions = int(
            (await self.client.count(index=self._versions_index, query={"term": {"state": NoteState.DRAFT.value}})).get(
                "count", 0
            )
        )
        needs_review_versions = int(
            (
                await self.client.count(
                    index=self._versions_index,
                    query={"term": {"state": NoteState.NEEDS_REVIEW.value}},
                )
            ).get("count", 0)
        )

        # `tags` and `created_by` are mapped as `keyword` types in the index mappings.
        # Use the field names directly for cardinality aggregation (no `.keyword` suffix).
        agg_response = await self.client.search(
            index=self._versions_index,
            size=0,
            aggs={
                "distinct_tags": {"cardinality": {"field": "tags"}},
                "active_authors": {"cardinality": {"field": "created_by"}},
            },
        )
        aggregations = agg_response.get("aggregations", {})
        distinct_tags = int(aggregations.get("distinct_tags", {}).get("value", 0))
        active_authors = int(aggregations.get("active_authors", {}).get("value", 0))

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
        await self._ensure_indices()
        review_id = uuid4().hex
        now = datetime.now(timezone.utc)
        review = Review(
            _id=review_id,
            note_id=note_id,
            draft_version_id=draft_version_id,
            base_version_id=base_version_id,
            title=title,
            description=description,
            created_by=created_by,
            reviewer_ids=reviewer_ids or [],
            status=ReviewStatus.OPEN,
            review_decisions={},
            merge_version_id=None,
            merged_by=None,
            created_at=now,
            updated_at=now,
            merged_at=None,
            closed_at=None,
        )
        # set explicit type if provided
        if review_type is not None:
            review.type = review_type
        await self.client.index(
            index=self._reviews_index,
            id=review_id,
            document=self._review_to_document(review),
            refresh="wait_for",
        )
        return review

    async def update_review(self, review_id: str, updates: Dict[str, object]) -> Optional[Review]:
        await self._ensure_indices()
        current = await self.get_review(review_id)
        if not current:
            return None

        data = current.model_dump()
        for key, value in updates.items():
            if isinstance(value, ReviewStatus):
                data[key] = value.value
            elif key == "review_decisions" and isinstance(value, dict):
                decisions: Dict[str, ReviewDecisionState] = {}
                for user_id, state in value.items():
                    if isinstance(state, ReviewDecisionState):
                        decisions[user_id] = state
                    elif isinstance(state, dict):
                        decisions[user_id] = ReviewDecisionState(
                            decision=ReviewDecision(state.get("decision")),
                            comment=state.get("comment"),
                            updated_at=state.get("updated_at", datetime.now(timezone.utc)),
                        )
                data[key] = decisions
            elif isinstance(value, ReviewDecisionState):
                data[key] = value
            else:
                data[key] = value

        if "updated_at" not in updates:
            data["updated_at"] = datetime.now(timezone.utc)

        updated = Review.model_validate(data)
        await self.client.index(
            index=self._reviews_index,
            id=review_id,
            document=self._review_to_document(updated),
            refresh="wait_for",
        )
        return updated

    async def get_review(self, review_id: str) -> Optional[Review]:
        await self._ensure_indices()
        try:
            doc = await self.client.get(index=self._reviews_index, id=review_id)
        except NotFoundError:
            return None
        return self._hit_to_review(doc)

    async def get_review_by_version(self, draft_version_id: str) -> Optional[Review]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._reviews_index,
            size=1,
            query={"term": {"draft_version_id": draft_version_id}},
        )
        hits = response.get("hits", {}).get("hits", [])
        if not hits:
            return None
        return self._hit_to_review(hits[0])

    async def get_reviews_by_version_ids(self, version_ids: Iterable[str]) -> Dict[str, Review]:
        await self._ensure_indices()
        ids = [version_id for version_id in set(version_ids) if version_id]
        if not ids:
            return {}
        response = await self.client.search(
            index=self._reviews_index,
            size=len(ids) * 2,
            query={"terms": {"draft_version_id": ids}},
        )
        results: Dict[str, Review] = {}
        for hit in response.get("hits", {}).get("hits", []):
            review = self._hit_to_review(hit)
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
        await self._ensure_indices()
        must_filters: List[Dict[str, Any]] = []
        if status:
            must_filters.append({"terms": {"status": [entry.value for entry in status]}})
        if created_by:
            must_filters.append({"term": {"created_by": created_by}})
        if reviewer_id:
            must_filters.append({"term": {"reviewer_ids": reviewer_id}})
        if note_id:
            must_filters.append({"term": {"note_id": note_id}})

        query: Dict[str, Any]
        if involved_user:
            involvement_filter = {
                "bool": {
                    "should": [
                        {"term": {"created_by": involved_user}},
                        {"term": {"reviewer_ids": involved_user}},
                    ],
                    "minimum_should_match": 1,
                }
            }
            if must_filters:
                query = {"bool": {"must": must_filters, "filter": [involvement_filter]}}
            else:
                query = involvement_filter
        else:
            if must_filters:
                query = {"bool": {"must": must_filters}}
            else:
                query = {"match_all": {}}

        response = await self.client.search(
            index=self._reviews_index,
            size=limit,
            sort=[{"updated_at": {"order": "desc"}}],
            query=query,
        )
        return [self._hit_to_review(hit) for hit in response.get("hits", {}).get("hits", [])]

    async def add_review_event(
        self,
        review_id: str,
        event_type: ReviewEventType,
        *,
        author_id: str,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> ReviewEvent:
        await self._ensure_indices()
        event_id = uuid4().hex
        event = ReviewEvent(
            _id=event_id,
            review_id=review_id,
            event_type=event_type,
            author_id=author_id,
            message=message,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
        )
        await self.client.index(
            index=self._review_events_index,
            id=event_id,
            document=self._review_event_to_document(event),
            refresh="wait_for",
        )
        return event

    async def list_review_events(self, review_id: str, limit: int = 200) -> List[ReviewEvent]:
        await self._ensure_indices()
        response = await self.client.search(
            index=self._review_events_index,
            size=limit,
            sort=[{"created_at": {"order": "asc"}}],
            query={"term": {"review_id": review_id}},
        )
        return [self._hit_to_review_event(hit) for hit in response.get("hits", {}).get("hits", [])]
