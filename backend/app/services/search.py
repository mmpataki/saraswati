from __future__ import annotations

from typing import List, Tuple

from ..models import NoteVersion
from ..repositories.interface import NotesRepositoryProtocol


async def hybrid_search(
    repository: NotesRepositoryProtocol,
    keyword: str | None = None,
    vector: List[float] | None = None,
    candidate_limit: int = 10,
) -> List[Tuple[NoteVersion, float]]:
    """Combine keyword and vector search signals."""

    results: List[Tuple[NoteVersion, float]] = []
    seen: dict[str, float] = {}

    if keyword is not None:
        keyword_matches = await repository.keyword_search(keyword, limit=candidate_limit)
        for rank, version in enumerate(keyword_matches, start=1):
            score = 1.0 - (rank - 1) / max(candidate_limit, 1)
            results.append((version, score))
            seen[version.id] = score

    if vector:
        vector_matches = await repository.vector_search(vector, limit=candidate_limit)
        for version, score in vector_matches:
            if version.id in seen:
                combined = (seen[version.id] + score) / 2
            else:
                combined = score
            seen[version.id] = combined
            results.append((version, combined))

    # Sort unique versions by combined score
    deduped: dict[str, Tuple[NoteVersion, float]] = {}
    for version, score in results:
        existing = deduped.get(version.id)
        if not existing or existing[1] < score:
            deduped[version.id] = (version, score)

    ordered = sorted(deduped.values(), key=lambda item: item[1], reverse=True)
    return ordered
