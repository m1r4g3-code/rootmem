"""Dict-backed `GraphRepository` fake — zero I/O, used by all unit tests.

Implements ADR 0008's deterministic contradiction rule directly (not via a
shared helper with the Postgres implementation) — the rule is simple enough
that duplicating it in each implementation is clearer than an abstraction
neither implementation would otherwise need, and the contract-test suite
holds both to the same observable behavior regardless.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from rootmem.storage.graph_models import (
    ContradictionResolution,
    EntityRecord,
    NewEntity,
    NewRelation,
    RelationRecord,
)
from rootmem.storage.graph_normalize import normalize_entity_name
from rootmem.storage.graph_protocols import NotFoundError


class InMemoryGraphRepository:
    def __init__(self, contradiction_confidence_floor: float = 0.5) -> None:
        self._entities: dict[str, EntityRecord] = {}
        self._relations: dict[str, RelationRecord] = {}
        self._memory_entities: set[tuple[str, str]] = set()
        self._contradiction_confidence_floor = contradiction_confidence_floor

    async def upsert_entity(self, entity: NewEntity) -> EntityRecord:
        existing = await self.find_entity_by_name(entity.namespace, entity.entity_type, entity.name)
        if existing is not None:
            return existing

        now = datetime.now(UTC)
        record = EntityRecord(
            id=str(uuid.uuid4()),
            namespace=entity.namespace,
            entity_type=entity.entity_type,
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
        for entity in self._entities.values():
            if (
                entity.namespace == namespace
                and entity.entity_type == entity_type
                and entity.canonical_key == canonical_key
            ):
                return entity
        return None

    async def create_relation(self, relation: NewRelation) -> ContradictionResolution:
        previous = self._find_active_relation(
            relation.namespace, relation.subject_entity_id, relation.predicate
        )

        now = datetime.now(UTC)
        new_id = str(uuid.uuid4())
        contested = (
            previous is not None and relation.confidence <= self._contradiction_confidence_floor
        )

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
            confidence=relation.confidence,
            valid_from=now,
            valid_to=None,
            recorded_at=now,
            supersedes=previous.id if (previous is not None and not contested) else None,
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
