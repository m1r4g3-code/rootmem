"""The graph storage port: `GraphRepository`.

A new, separate Protocol from `MemoryRepository` (ADR 0006) — entities and
relations are a genuinely different aggregate (bi-temporal validity, not
soft-delete-via-single-timestamp). Extraction/capture code depends only on
this Protocol, never on a concrete driver directly, same discipline ADR
0003 established for `MemoryRepository`. `InMemoryGraphRepository` and
`PostgresGraphRepository` both satisfy it and are verified against the same
contract-test suite (`tests/unit/storage/graph_contract.py`) for behavioral
parity.
"""

from __future__ import annotations

from typing import Protocol

from rootmem.storage.graph_models import (
    ContradictionResolution,
    EntityRecord,
    NewEntity,
    NewRelation,
    RelationRecord,
)
from rootmem.storage.protocols import NotFoundError, StorageError

__all__ = ["GraphRepository", "NotFoundError", "StorageError"]


class GraphRepository(Protocol):
    async def upsert_entity(self, entity: NewEntity) -> EntityRecord:
        """Create an entity, or return the existing one if an entity with the
        same (namespace, entity_type, canonical_key) already exists.

        This is Phase 1's deliberately minimal entity resolution (exact
        normalized-key match only — see docs/research/phase1-research-memo.md).
        """
        ...

    async def get_entity_by_id(self, namespace: str, entity_id: str) -> EntityRecord | None:
        """Return the entity, or None if it doesn't exist in this namespace."""
        ...

    async def find_entity_by_name(
        self, namespace: str, entity_type: str, name: str
    ) -> EntityRecord | None:
        """Look up an entity by its normalized name, or None if none exists."""
        ...

    async def create_relation(self, relation: NewRelation) -> ContradictionResolution:
        """Create a new relation, applying ADR 0008's deterministic
        contradiction rule against any currently-active relation for the
        same (namespace, subject_entity_id, predicate):

        - If there's no active relation to contradict: the new relation is
          simply created active. `ContradictionResolution.previous` is None.
        - If there is one, and the new relation's confidence exceeds the
          configured floor: the previous relation is superseded (`valid_to`
          set to the new relation's `valid_from`, `superseded_by` set to the
          new relation's id; the new relation's `supersedes` is set to the
          previous relation's id).
        - If there is one, but the new relation's confidence does not exceed
          the floor: both relations are marked `metadata.contested = true`
          and remain active — neither is superseded.

        Never deletes or overwrites a row (ADR 0004's soft-delete
        discipline, extended to the graph by ADR 0008).
        """
        ...

    async def get_relation_by_id(self, namespace: str, relation_id: str) -> RelationRecord | None:
        """Return the relation, or None if it doesn't exist in this namespace."""
        ...

    async def related(
        self, namespace: str, entity_id: str, max_hops: int = 1
    ) -> list[RelationRecord]:
        """Return every relation (active or superseded) touching `entity_id`
        as subject or object, up to `max_hops` hops away. Includes
        superseded relations with their full `valid_from`/`valid_to` history
        — this is what makes the bi-temporal record inspectable, not just
        the currently-active view."""
        ...

    async def link_memory_entity(self, memory_id: str, entity_id: str) -> None:
        """Record that `entity_id` was extracted from `memory_id` (the
        `memory_entities` join table). Idempotent — linking the same pair
        twice is a no-op, since `extraction.pipeline` may re-link an entity
        already mentioned earlier in the same memory."""
        ...
