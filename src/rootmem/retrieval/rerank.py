"""Multi-factor re-ranking of memory search candidates (ADR 0022).

The repository returns relevance-ordered candidates; this layer scores each
with `rank_score` over relevance, retention R(t), salience, trust and graph
proximity, then reorders. Everything numeric lives in pure modules
(`ranking`, `decay`, `trust.scoring`); this file only gathers their inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from rootmem.config import Settings
from rootmem.retrieval.decay import RetentionParams, retention
from rootmem.retrieval.ranking import RankedScore, RankTerms, RankWeights, rank_score
from rootmem.storage.graph_models import EntityRecord
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.models import SearchResult
from rootmem.trust.scoring import TrustParams, memory_trust


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RankingContext:
    weights: RankWeights
    retention: RetentionParams
    trust: TrustParams
    overfetch: int = 3
    clock: Callable[[], datetime] = _utc_now

    @classmethod
    def from_settings(
        cls, settings: Settings, clock: Callable[[], datetime] = _utc_now
    ) -> RankingContext:
        return cls(
            weights=RankWeights(
                relevance=settings.rank_weight_relevance,
                retention=settings.rank_weight_retention,
                salience=settings.rank_weight_salience,
                trust=settings.rank_weight_trust,
                graph_proximity=settings.rank_weight_graph_proximity,
            ),
            retention=RetentionParams(base_stability_days=settings.decay_base_stability_days),
            trust=TrustParams(
                default_reliability=settings.trust_default_reliability,
                source_reliability=dict(settings.trust_source_reliability),
            ),
            overfetch=settings.rank_candidate_overfetch,
            clock=clock,
        )


async def _graph_proximity(
    hits: list[SearchResult],
    namespace: str,
    entity: EntityRecord,
    graph_repository: GraphRepository,
) -> dict[str, float]:
    """1.0 when the memory is linked to `entity`, 0.5 when linked to a 1-hop
    neighbour of it, else 0.0."""
    memory_ids = [hit.record.id for hit in hits]
    linked = await graph_repository.entity_ids_for_memories(namespace, memory_ids)
    relations = await graph_repository.related(namespace, entity.id, max_hops=1)
    neighbours: set[str] = set()
    for relation in relations:
        neighbours.add(relation.subject_entity_id)
        if relation.object_entity_id is not None:
            neighbours.add(relation.object_entity_id)
    neighbours.discard(entity.id)

    proximity: dict[str, float] = {}
    for memory_id in memory_ids:
        entities = linked.get(memory_id, set())
        if entity.id in entities:
            proximity[memory_id] = 1.0
        elif entities & neighbours:
            proximity[memory_id] = 0.5
        else:
            proximity[memory_id] = 0.0
    return proximity


async def rerank_memory_hits(
    hits: list[SearchResult],
    namespace: str,
    context: RankingContext,
    now: datetime,
    graph_repository: GraphRepository | None = None,
    entity: EntityRecord | None = None,
) -> list[tuple[SearchResult, RankedScore]]:
    """Return `hits` reordered by descending multi-factor score, each paired
    with its `RankedScore`. Ties keep the incoming (relevance) order."""
    proximity: dict[str, float] | None = None
    if entity is not None and graph_repository is not None:
        proximity = await _graph_proximity(hits, namespace, entity, graph_repository)

    scored: list[tuple[SearchResult, RankedScore]] = []
    for hit in hits:
        record = hit.record
        terms = RankTerms(
            relevance=hit.score,
            retention=retention(
                now,
                record.last_accessed_at,
                record.created_at,
                record.access_count,
                record.salience_score,
                context.retention,
            ),
            salience=record.salience_score,
            trust=memory_trust(record.source, record.confidence, context.trust),
            graph_proximity=proximity[record.id] if proximity is not None else None,
        )
        scored.append((hit, rank_score(terms, context.weights)))
    scored.sort(key=lambda pair: pair[1].score, reverse=True)
    return scored
