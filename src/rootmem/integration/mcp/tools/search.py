"""`search` — text, semantic, or hybrid search over non-deleted memories
(`params.mode`, default "hybrid" — ADR 0007), re-ranked by the Phase 4
multi-factor score (ADR 0022) when a `RankingContext` is supplied.

Phase 0's naive full-text ranking (`docs/math-spec/phase0-math-spec.md`)
still backs `mode="text"` unchanged. "semantic"/"hybrid" need a query
embedding first; if the embedding provider fails, this degrades to plain
text search regardless of the requested mode (NFR2) rather than raising —
a query embedding failure should reduce search quality, not break search.

Without a `RankingContext` the repository's relevance order is returned
untouched (the pre-Phase-4 behavior).
"""

from __future__ import annotations

from datetime import datetime

from rootmem.embedding.protocols import EmbeddingProvider, embed_or_none
from rootmem.integration.mcp.schemas import SearchParams, SearchResponse, SearchResultItem
from rootmem.logging import get_logger
from rootmem.observability.metrics import log_operation
from rootmem.retrieval.ranking import RankedScore
from rootmem.retrieval.rerank import RankingContext, rerank_memory_hits
from rootmem.storage.graph_models import EntityRecord
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.models import SearchResult
from rootmem.storage.protocols import MemoryRepository


async def _candidates(
    repository: MemoryRepository,
    embedding_provider: EmbeddingProvider,
    params: SearchParams,
    fetch_limit: int,
) -> list[SearchResult]:
    if params.mode == "text":
        return await repository.search_text(
            params.namespace, params.query, fetch_limit, source=params.source
        )
    query_embedding = await embed_or_none(embedding_provider, params.query)
    if query_embedding is None:
        return await repository.search_text(
            params.namespace, params.query, fetch_limit, source=params.source
        )
    if params.mode == "semantic":
        return await repository.search_semantic(
            params.namespace, query_embedding, fetch_limit, source=params.source
        )
    return await repository.search_hybrid(
        params.namespace, params.query, query_embedding, fetch_limit, source=params.source
    )


async def _record_access(
    repository: MemoryRepository,
    ranked: list[tuple[SearchResult, RankedScore]],
    now: datetime,
    params: SearchParams,
) -> None:
    """Reads reinforce memory (ADR 0023), except what-if (`as_of`) queries,
    which must not mutate. A tracking failure never fails the search."""
    if params.as_of is not None or not ranked:
        return
    try:
        await repository.record_access([hit.record.id for hit, _ in ranked], now)
    except Exception:  # noqa: BLE001 - tracking is best-effort by design
        get_logger().warning("record_access failed; search result unaffected", exc_info=True)


@log_operation("search")
async def search(
    repository: MemoryRepository,
    embedding_provider: EmbeddingProvider,
    params: SearchParams,
    ranking: RankingContext | None = None,
    graph_repository: GraphRepository | None = None,
) -> SearchResponse:
    if ranking is None:
        hits = await _candidates(repository, embedding_provider, params, params.limit)
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

    candidates = await _candidates(
        repository, embedding_provider, params, params.limit * ranking.overfetch
    )
    entity: EntityRecord | None = None
    if (
        graph_repository is not None
        and params.entity_name is not None
        and params.entity_type is not None
    ):
        entity = await graph_repository.find_entity_by_name(
            params.namespace, params.entity_type, params.entity_name
        )

    now = params.as_of if params.as_of is not None else ranking.clock()
    reranked = await rerank_memory_hits(
        candidates, params.namespace, ranking, now, graph_repository, entity
    )
    ranked = reranked[: params.limit]
    await _record_access(repository, ranked, now, params)

    return SearchResponse(
        results=[
            SearchResultItem(
                id=hit.record.id,
                content=hit.record.content,
                key=hit.record.key,
                score=scored.score,
                source=hit.record.source,
                created_at=hit.record.created_at,
                breakdown=scored.breakdown,
            )
            for hit, scored in ranked
        ]
    )
