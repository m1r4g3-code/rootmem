"""`find_skill` — hybrid text+vector search over distilled procedural
memories (skills/lessons), ranked by real content, not name-matching (ADR
0017). Degrades to text-only ranking if the query embedding fails (NFR2's
established "degrade, don't break search" discipline, same as `search`).
"""

from __future__ import annotations

from rootmem.embedding.protocols import EmbeddingProvider, embed_or_none
from rootmem.integration.mcp.schemas import FindSkillParams, FindSkillResult, SkillSearchResultItem
from rootmem.observability.metrics import log_operation
from rootmem.storage.procedural_protocols import ProceduralMemoryRepository


@log_operation("find_skill")
async def find_skill(
    procedural_memory_repository: ProceduralMemoryRepository,
    embedding_provider: EmbeddingProvider,
    params: FindSkillParams,
) -> FindSkillResult:
    query_embedding = await embed_or_none(embedding_provider, params.query)
    hits = await procedural_memory_repository.search_hybrid(
        params.namespace, params.query, query_embedding, kind=params.kind, limit=params.limit
    )
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
