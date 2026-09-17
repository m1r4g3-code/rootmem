"""Materializes an `ExtractionResult` (entity/relation *names*) into the
graph store (entity/relation *ids*).

The Bayesian contradiction/corroboration decision itself (ADR 0013) already
lives inside `GraphRepository.create_relation` — both implementations apply
it identically, verified by the shared graph contract-test suite
(tests/unit/storage/graph_contract.py). This module's job is narrower: name
resolution (upserting entities so relations can reference ids) and calling
`create_relation`/`link_memory_entity`/`link_relation_provenance` in the
right order — it does not re-decide anything `create_relation` already
decides.

Generalized in Phase 2 (ADR 0016) to serve both extraction (one source
episode) and distillation (a cluster of several source episodes): a single
id preserves Phase 1's exact observable behavior (`source_memory_id` set on
the relation, for existing consumers), while multiple ids fall back to
`relation_provenance` links only -- there's no single "the" source once a
fact was abstracted across a cluster.
"""

from __future__ import annotations

from typing import Literal

from rootmem.extraction.models import ApplyExtractionResult, ExtractionResult
from rootmem.storage.graph_models import ContradictionResolution, NewEntity, NewRelation
from rootmem.storage.graph_protocols import GraphRepository


async def apply_extraction(
    graph: GraphRepository,
    namespace: str,
    result: ExtractionResult,
    source_memory_ids: list[str] | None = None,
    derivation: Literal["extracted", "distilled"] = "extracted",
) -> ApplyExtractionResult:
    """Upsert every entity `result` names, create every relation it
    describes (resolving subject/object names to entity ids first), and
    link each entity/relation to every id in `source_memory_ids`, if any are
    given."""
    entity_ids: dict[tuple[str, str], str] = {}

    async def _resolve(name: str, entity_type: str) -> str:
        key = (name, entity_type)
        if key not in entity_ids:
            entity = await graph.upsert_entity(
                NewEntity(namespace=namespace, entity_type=entity_type, name=name)
            )
            entity_ids[key] = entity.id
        return entity_ids[key]

    for extracted_entity in result.entities:
        await _resolve(extracted_entity.name, extracted_entity.entity_type)

    # A single source preserves Phase 1's exact observable behavior
    # (relations.source_memory_id set); several sources (distillation) have
    # no single "the" source, so it stays None and relation_provenance
    # carries the full set instead.
    single_source_memory_id = (
        source_memory_ids[0] if source_memory_ids and len(source_memory_ids) == 1 else None
    )

    resolutions: list[ContradictionResolution] = []
    for relation in result.relations:
        subject_id = await _resolve(relation.subject_name, relation.subject_type)
        object_entity_id = None
        if relation.object_name is not None:
            assert relation.object_type is not None  # enforced by ExtractedRelation's validator
            object_entity_id = await _resolve(relation.object_name, relation.object_type)

        resolution = await graph.create_relation(
            NewRelation(
                namespace=namespace,
                subject_entity_id=subject_id,
                predicate=relation.predicate,
                object_entity_id=object_entity_id,
                object_literal=relation.object_literal,
                confidence=relation.confidence,
                derivation=derivation,
                source_memory_id=single_source_memory_id,
            )
        )
        resolutions.append(resolution)

        for memory_id in source_memory_ids or []:
            await graph.link_relation_provenance(resolution.new.id, memory_id)

    for entity_id in entity_ids.values():
        for memory_id in source_memory_ids or []:
            await graph.link_memory_entity(memory_id, entity_id)

    return ApplyExtractionResult(resolutions=resolutions, entity_ids=list(entity_ids.values()))
