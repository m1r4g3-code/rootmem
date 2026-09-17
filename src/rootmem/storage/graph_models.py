"""Domain model for the bi-temporal semantic graph — entities and relations.

A genuinely different aggregate from `storage.models.MemoryRecord`: entities
and relations have bi-temporal validity (`valid_from`/`valid_to`), not
`MemoryRecord`'s single-timestamp soft-delete. See ADR 0006 for why this is
plain Postgres tables rather than a dedicated graph engine, and ADR 0008 for
the contradiction-resolution semantics `RelationRecord.supersedes`/
`superseded_by` encode.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityRecord(BaseModel):
    """A single entity row.

    `canonical_key` is the normalized form of `name` used for Phase 1's
    deliberately minimal dedup (exact match within `namespace`+`entity_type`
    only — see docs/research/phase1-research-memo.md's entity-resolution
    open item).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    namespace: str
    entity_type: str
    name: str
    canonical_key: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: datetime


class NewEntity(BaseModel):
    """Input to `GraphRepository.upsert_entity` — no id/timestamps, assigned by
    the store. `canonical_key` is deliberately not a caller-supplied field:
    the repository computes it from `name` internally (see
    `storage.graph_normalize.normalize_entity_name`), so there is exactly one
    place that decides what "the same entity" means, not two that could
    silently drift apart."""

    namespace: str
    entity_type: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class RelationRecord(BaseModel):
    """A single relation (edge) row.

    Bi-temporal: `valid_from`/`valid_to` is valid time (when the fact was/is
    true in the world); `recorded_at` is transaction time (when this system
    learned it). `valid_to is None` means the relation is currently active.

    A contradiction never deletes a row (ADR 0004's soft-delete philosophy,
    extended to the graph by ADR 0008, now decided by ADR 0013's Bayesian
    update instead of a flat floor): the loser gets `valid_to` and
    `superseded_by` set; the winner gets `supersedes` set.

    `confidence` is a cached, recomputed function of `belief_alpha`/
    `belief_beta` (ADR 0013) — `confidence = belief_alpha / (belief_alpha +
    belief_beta)` — never independently assigned by a caller. See
    `extraction.contradiction` for the update logic.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    namespace: str

    subject_entity_id: str
    predicate: str
    object_entity_id: str | None = None
    object_literal: str | None = None

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    belief_alpha: float = Field(default=1.0, gt=0.0)
    belief_beta: float = Field(default=1.0, gt=0.0)

    valid_from: datetime
    valid_to: datetime | None = None
    recorded_at: datetime

    supersedes: str | None = None
    superseded_by: str | None = None

    derivation: Literal["extracted", "distilled"] = "extracted"
    source_memory_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.valid_to is None

    @property
    def is_contested(self) -> bool:
        return bool(self.metadata.get("contested", False))


class NewRelation(BaseModel):
    """Input to `GraphRepository.create_relation` — no id/timestamps, assigned by the store.
    `belief_alpha`/`belief_beta` are not caller-supplied: they are computed
    internally by `extraction.contradiction.resolve_contradiction` from
    `confidence` and `derivation`, the same "exactly one place decides"
    discipline `NewEntity.canonical_key` already established."""

    namespace: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None = None
    object_literal: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    derivation: Literal["extracted", "distilled"] = "extracted"
    source_memory_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _object_present(self) -> NewRelation:
        if self.object_entity_id is None and self.object_literal is None:
            raise ValueError("relation must have object_entity_id or object_literal")
        return self


class ContradictionResolution(BaseModel):
    """Result of resolving a new relation against the currently-active one
    for the same `(namespace, subject_entity_id, predicate)`, per ADR 0013's
    Bayesian belief update. `previous` is None when there was no active
    relation to contradict, or when the exact-match `corroborated` case
    updated the existing relation's belief in place rather than superseding
    it — either way, no row was superseded. `new` is the relation the
    caller should treat as authoritative: a freshly created row (`create`/
    `supersede`/`contest`), or the same row `previous` referred to before,
    now with an updated belief (`corroborate`)."""

    model_config = ConfigDict(frozen=True)

    new: RelationRecord
    previous: RelationRecord | None
    contested: bool
    corroborated: bool = False
