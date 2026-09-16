"""`search` — text, semantic, or hybrid search over non-deleted memories
(`params.mode`, default "hybrid" — ADR 0007).

Phase 0's naive full-text ranking (`docs/math-spec/phase0-math-spec.md`)
still backs `mode="text"` unchanged. "semantic"/"hybrid" need a query
embedding first; if the embedding provider fails, this degrades to plain
text search regardless of the requested mode (NFR2) rather than raising —
a query embedding failure should reduce search quality, not break search.
"""

from __future__ import annotations

from rootmem.embedding.protocols import EmbeddingProvider, embed_or_none
from rootmem.integration.mcp.schemas import SearchParams, SearchResponse, SearchResultItem
from rootmem.observability.metrics import log_operation
from rootmem.storage.models import SearchResult
from rootmem.storage.protocols import MemoryRepository


@log_operation("search")
async def search(
    repository: MemoryRepository,
    embedding_provider: EmbeddingProvider,
    params: SearchParams,
) -> SearchResponse:
    hits: list[SearchResult]
    if params.mode == "text":
        hits = await repository.search_text(
            params.namespace, params.query, params.limit, source=params.source
        )
    else:
        query_embedding = await embed_or_none(embedding_provider, params.query)
        if query_embedding is None:
            hits = await repository.search_text(
                params.namespace, params.query, params.limit, source=params.source
            )
        elif params.mode == "semantic":
            hits = await repository.search_semantic(
                params.namespace, query_embedding, params.limit, source=params.source
            )
        else:
            hits = await repository.search_hybrid(
                params.namespace, params.query, query_embedding, params.limit, source=params.source
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
