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

from typing import Literal, Protocol

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
        """Create or corroborate a relation, applying ADR 0013's Bayesian
        belief update (`extraction.contradiction.resolve_contradiction`)
        against any currently-active relation for the same
        (namespace, subject_entity_id, predicate):

        - No active relation exists: `relation` is created active with a
          fresh belief (`Beta(1,1)` prior plus this one event).
          `ContradictionResolution.previous` is None.
        - An active relation exists with the *same* object
          (`object_entity_id`/`object_literal`): this is corroboration, not
          a contradiction. No new row is created — the *existing* relation's
          belief is strengthened in place and returned as `new`.
          `ContradictionResolution.corroborated` is True, `previous` is None
          (nothing was superseded).
        - An active relation exists with a *different* object: a candidate
          contradiction. The new relation's own belief is computed fresh; if
          its posterior confidence exceeds the existing relation's by
          `bayesian_supersede_margin`, the existing relation is superseded
          (`valid_to` set to the new relation's `valid_from`,
          `superseded_by` set to the new relation's id; the new relation's
          `supersedes` is set to the previous relation's id). Otherwise both
          relations are marked `metadata.contested = true` and remain
          active — neither is superseded.

        Never deletes or overwrites a row (ADR 0004's soft-delete
        discipline, extended to the graph by ADR 0008 and refined by ADR
        0013's Bayesian decision function).
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

    async def entity_ids_for_memories(
        self, namespace: str, memory_ids: list[str]
    ) -> dict[str, set[str]]:
        """For each memory id, the ids of entities linked to it via
        `memory_entities` (ADR 0022's `graph_proximity` input). Memories with
        no links are omitted from the result."""
        ...

    async def link_relation_provenance(self, relation_id: str, memory_id: str) -> None:
        """Record that `relation_id` was derived (extracted or distilled)
        from `memory_id` (the `relation_provenance` join table). Idempotent,
        same rationale as `link_memory_entity`. A relation created by
        extraction links exactly one memory; one created by distillation
        (ADR 0015/0016) links every episode in its source cluster."""
        ...

    async def get_relation_provenance(self, namespace: str, relation_id: str) -> list[str]:
        """Return the memory ids `relation_id` was derived from — one for an
        extracted relation, several for a distilled one."""
        ...

    async def record_feedback(
        self,
        namespace: str,
        relation_id: str,
        outcome: Literal["confirmed", "contradicted"],
        reported_confidence: float,
        note: str | None,
    ) -> RelationRecord:
        """Record a `relation_feedback` row and apply
        `extraction.contradiction.apply_feedback` (ADR 0013/0014) to
        `relation_id`'s belief, returning the relation with its recomputed
        `confidence`. Raises `NotFoundError` if `relation_id` doesn't exist
        in this namespace."""
        ...
