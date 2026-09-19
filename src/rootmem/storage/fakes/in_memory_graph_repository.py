"""Dict-backed `GraphRepository` fake — zero I/O, used by all unit tests.

`create_relation`/`record_feedback` both call the shared
`extraction.contradiction` pure functions (ADR 0013) — the Bayesian math is
written once and called by both this fake and `PostgresGraphRepository`,
closing the gap ADR 0008's deterministic rule left (it was duplicated inline
in each implementation instead).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from rootmem.extraction.contradiction import BayesianSettings, apply_feedback, resolve_contradiction
from rootmem.storage.graph_models import (
    ContradictionResolution,
    EntityRecord,
    NewEntity,
    NewRelation,
    RelationRecord,
)
from rootmem.storage.graph_normalize import normalize_entity_name, normalize_entity_type
from rootmem.storage.graph_protocols import NotFoundError


class InMemoryGraphRepository:
    def __init__(self, bayesian_settings: BayesianSettings | None = None) -> None:
        self._entities: dict[str, EntityRecord] = {}
        self._relations: dict[str, RelationRecord] = {}
        self._memory_entities: set[tuple[str, str]] = set()
        self._relation_provenance: set[tuple[str, str]] = set()
        self._bayesian_settings = bayesian_settings or BayesianSettings(
            prior_strength=2.0,
            supersede_margin=0.05,
            reliability_extracted=0.7,
            reliability_distilled=0.85,
            reliability_feedback=1.0,
        )

    async def upsert_entity(self, entity: NewEntity) -> EntityRecord:
        existing = await self.find_entity_by_name(entity.namespace, entity.entity_type, entity.name)
        if existing is not None:
            return existing

        now = datetime.now(UTC)
        record = EntityRecord(
            id=str(uuid.uuid4()),
            namespace=entity.namespace,
            entity_type=normalize_entity_type(entity.entity_type),
            name=entity.name,
            canonical_key=normalize_entity_name(entity.name),
            attributes=entity.attributes,
            created_at=now,
            updated_at=now,
        )
        self._entities[record.id] = record
        return record

    async def get_entity_by_id(self, namespace: str, entity_id: str) -> EntityRecord | None:
        entity = self._entities.get(entity_id)
        if entity is None or entity.namespace != namespace:
            return None
        return entity

    async def find_entity_by_name(
        self, namespace: str, entity_type: str, name: str
    ) -> EntityRecord | None:
        canonical_key = normalize_entity_name(name)
        canonical_type = normalize_entity_type(entity_type)
        for entity in self._entities.values():
            if (
                entity.namespace == namespace
                and entity.entity_type == canonical_type
                and entity.canonical_key == canonical_key
            ):
                return entity
        return None

    async def create_relation(self, relation: NewRelation) -> ContradictionResolution:
        previous = self._find_active_relation(
            relation.namespace, relation.subject_entity_id, relation.predicate
        )
        decision = resolve_contradiction(
            previous, relation, relation.derivation, self._bayesian_settings
        )

        if decision.action == "corroborate":
            assert previous is not None
            updated = previous.model_copy(
                update={
                    "belief_alpha": decision.belief_alpha,
                    "belief_beta": decision.belief_beta,
                    "confidence": decision.belief_alpha
                    / (decision.belief_alpha + decision.belief_beta),
                    "derivation": decision.derivation,
                }
            )
            self._relations[updated.id] = updated
            return ContradictionResolution(
                new=updated, previous=None, contested=False, corroborated=True
            )

        now = datetime.now(UTC)
        new_id = str(uuid.uuid4())
        contested = decision.action == "contest"

        new_metadata = dict(relation.metadata)
        if contested:
            new_metadata["contested"] = True

        new_record = RelationRecord(
            id=new_id,
            namespace=relation.namespace,
            subject_entity_id=relation.subject_entity_id,
            predicate=relation.predicate,
            object_entity_id=relation.object_entity_id,
            object_literal=relation.object_literal,
            confidence=decision.belief_alpha / (decision.belief_alpha + decision.belief_beta),
            belief_alpha=decision.belief_alpha,
            belief_beta=decision.belief_beta,
            valid_from=now,
            valid_to=None,
            recorded_at=now,
            supersedes=previous.id if (previous is not None and not contested) else None,
            derivation=relation.derivation,
            source_memory_id=relation.source_memory_id,
            metadata=new_metadata,
        )
        self._relations[new_id] = new_record

        if previous is not None:
            if contested:
                previous_metadata = dict(previous.metadata)
                previous_metadata["contested"] = True
                previous = previous.model_copy(update={"metadata": previous_metadata})
            else:
                previous = previous.model_copy(update={"valid_to": now, "superseded_by": new_id})
            self._relations[previous.id] = previous

        return ContradictionResolution(new=new_record, previous=previous, contested=contested)

    async def get_relation_by_id(self, namespace: str, relation_id: str) -> RelationRecord | None:
        relation = self._relations.get(relation_id)
        if relation is None or relation.namespace != namespace:
            return None
        return relation

    async def related(
        self, namespace: str, entity_id: str, max_hops: int = 1
    ) -> list[RelationRecord]:
        if max_hops < 1:
            return []

        frontier = {entity_id}
        visited_entities = {entity_id}
        results: list[RelationRecord] = []
        seen_relation_ids: set[str] = set()

        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for relation in self._relations.values():
                if relation.namespace != namespace:
                    continue
                touches = (
                    relation.subject_entity_id in frontier or relation.object_entity_id in frontier
                )
                if not touches or relation.id in seen_relation_ids:
                    continue
                seen_relation_ids.add(relation.id)
                results.append(relation)
                for candidate in (relation.subject_entity_id, relation.object_entity_id):
                    if candidate is not None and candidate not in visited_entities:
                        next_frontier.add(candidate)
                        visited_entities.add(candidate)
            frontier = next_frontier
            if not frontier:
                break

        return results

    async def link_memory_entity(self, memory_id: str, entity_id: str) -> None:
        self._memory_entities.add((memory_id, entity_id))

    async def entity_ids_for_memories(
        self, namespace: str, memory_ids: list[str]
    ) -> dict[str, set[str]]:
        wanted = set(memory_ids)
        result: dict[str, set[str]] = {}
        for memory_id, entity_id in self._memory_entities:
            entity = self._entities.get(entity_id)
            if memory_id in wanted and entity is not None and entity.namespace == namespace:
                result.setdefault(memory_id, set()).add(entity_id)
        return result

    async def link_relation_provenance(self, relation_id: str, memory_id: str) -> None:
        self._relation_provenance.add((relation_id, memory_id))

    async def get_relation_provenance(self, namespace: str, relation_id: str) -> list[str]:
        return [
            memory_id
            for rel_id, memory_id in self._relation_provenance
            if rel_id == relation_id and relation_id in self._relations
        ]

    async def record_feedback(
        self,
        namespace: str,
        relation_id: str,
        outcome: Literal["confirmed", "contradicted"],
        reported_confidence: float,
        note: str | None,
    ) -> RelationRecord:
        relation = self._relations.get(relation_id)
        if relation is None or relation.namespace != namespace:
            raise NotFoundError(f"relation {relation_id} not found in namespace {namespace}")

        new_alpha, new_beta = apply_feedback(
            relation.belief_alpha,
            relation.belief_beta,
            outcome=outcome,
            reported_confidence=reported_confidence,
            settings=self._bayesian_settings,
        )
        updated = relation.model_copy(
            update={
                "belief_alpha": new_alpha,
                "belief_beta": new_beta,
                "confidence": new_alpha / (new_alpha + new_beta),
            }
        )
        self._relations[relation_id] = updated
        return updated

    @property
    def memory_entity_links(self) -> frozenset[tuple[str, str]]:
        """Test-only introspection — no `GraphRepository` Protocol method
        surfaces `memory_entities` reads yet (no MCP tool needs it in Phase
        1), but tests of *this fake's* behavior specifically need a way to
        observe what `link_memory_entity` recorded."""
        return frozenset(self._memory_entities)

    def _find_active_relation(
        self, namespace: str, subject_entity_id: str, predicate: str
    ) -> RelationRecord | None:
        for relation in self._relations.values():
            if (
                relation.namespace == namespace
                and relation.subject_entity_id == subject_entity_id
                and relation.predicate == predicate
                and relation.valid_to is None
            ):
                return relation
        return None


__all__ = ["InMemoryGraphRepository", "NotFoundError"]
