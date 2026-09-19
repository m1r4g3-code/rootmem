"""`find_skill` — hybrid text+vector search over distilled procedural
memories (skills/lessons), ranked by real content, not name-matching (ADR
0017). Degrades to text-only ranking if the query embedding fails (NFR2's
established "degrade, don't break search" discipline, same as `search`).

With a `RankingContext` (Phase 4, ADR 0022/0024) candidates are re-ranked so
that a skill's demonstrated effectiveness contributes as its trust term.
"""

from __future__ import annotations

from rootmem.embedding.protocols import EmbeddingProvider, embed_or_none
from rootmem.integration.mcp.schemas import FindSkillParams, FindSkillResult, SkillSearchResultItem
from rootmem.observability.metrics import log_operation
from rootmem.retrieval.ranking import RankTerms, rank_score
from rootmem.retrieval.rerank import RankingContext
from rootmem.storage.procedural_protocols import ProceduralMemoryRepository
from rootmem.trust.scoring import skill_effectiveness


@log_operation("find_skill")
async def find_skill(
    procedural_memory_repository: ProceduralMemoryRepository,
    embedding_provider: EmbeddingProvider,
    params: FindSkillParams,
    ranking: RankingContext | None = None,
) -> FindSkillResult:
    query_embedding = await embed_or_none(embedding_provider, params.query)
    fetch_limit = params.limit * ranking.overfetch if ranking is not None else params.limit
    hits = await procedural_memory_repository.search_hybrid(
        params.namespace, params.query, query_embedding, kind=params.kind, limit=fetch_limit
    )
    if ranking is None:
        return FindSkillResult(
            results=[
                SkillSearchResultItem(
                    name=hit.record.name,
                    kind=hit.record.kind,
                    description=hit.record.description,
                    score=hit.score,
                )
                for hit in hits
            ]
        )

    items: list[SkillSearchResultItem] = []
    for hit in hits:
        effectiveness = skill_effectiveness(hit.record.belief_alpha, hit.record.belief_beta)
        ranked = rank_score(RankTerms(relevance=hit.score, trust=effectiveness), ranking.weights)
        items.append(
            SkillSearchResultItem(
                name=hit.record.name,
                kind=hit.record.kind,
                description=hit.record.description,
                score=ranked.score,
                effectiveness=effectiveness,
                breakdown=ranked.breakdown,
            )
        )
    items.sort(key=lambda item: item.score, reverse=True)
    return FindSkillResult(results=items[: params.limit])
