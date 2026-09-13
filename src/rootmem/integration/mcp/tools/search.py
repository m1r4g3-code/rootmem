"""`search` — ranked full-text search over non-deleted memories.

Ranking is deliberately naive in Phase 0 (Postgres `ts_rank()` in
production, occurrence-count in the in-memory fake) — see
docs/math-spec/phase0-math-spec.md for why no custom scoring formula
belongs here yet.
"""

from __future__ import annotations

from rootmem.integration.mcp.schemas import SearchParams, SearchResponse, SearchResultItem
from rootmem.observability.metrics import log_operation
from rootmem.storage.protocols import MemoryRepository


@log_operation("search")
async def search(repository: MemoryRepository, params: SearchParams) -> SearchResponse:
    hits = await repository.search_text(
        params.namespace, params.query, params.limit, source=params.source
    )
    return SearchResponse(
        results=[
            SearchResultItem(
                id=hit.record.id,
                content=hit.record.content,
                key=hit.record.key,
                score=hit.score,
                source=hit.record.source,
                created_at=hit.record.created_at,
            )
            for hit in hits
        ]
    )
