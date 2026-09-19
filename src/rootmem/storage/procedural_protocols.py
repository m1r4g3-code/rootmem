"""The procedural memory storage port: `ProceduralMemoryRepository`.

A new, separate Protocol from `MemoryRepository`/`GraphRepository`/
`ConsolidationRepository` (ADR 0017) -- a distilled skill/lesson artifact is
neither a raw episode, a graph fact, nor a consolidation run record, the same
"genuinely different aggregate" test ADR 0006/0016 already used to justify
`GraphRepository`/`ConsolidationRepository`'s own separateness.
`InMemoryProceduralMemoryRepository` and `PostgresProceduralMemoryRepository`
both satisfy it and are verified against the same contract-test suite
(`tests/unit/storage/procedural_contract.py`) for behavioral parity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class ProceduralMemoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    namespace: str
    kind: Literal["skill", "lesson"]
    name: str
    description: str
    body_markdown: str
    content_embedding: list[float] | None = None
    derivation: Literal["distilled"] = "distilled"
    supersedes: str | None = None
    superseded_by: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_reason: str | None = None
    # Phase 4 (ADR 0024): effectiveness as a Beta posterior over "this works",
    # fed only by `record_outcome` (the explicit report_skill_outcome tool).
    belief_alpha: float = 1.0
    belief_beta: float = 1.0
    applied_count: int = 0
    success_count: int = 0

    @property
    def is_active(self) -> bool:
        return self.superseded_by is None and self.deleted_at is None


class NewProceduralMemory(BaseModel):
    """Input to `ProceduralMemoryRepository.create` -- no id/timestamps,
    those are assigned by the store."""

    namespace: str
    kind: Literal["skill", "lesson"]
    name: str
    description: str
    body_markdown: str
    content_embedding: list[float] | None = None


class ProceduralSearchResult(BaseModel):
    """One ranked hit from `ProceduralMemoryRepository.search_hybrid`."""

    record: ProceduralMemoryRecord
    score: float


class ProceduralMemoryRepository(Protocol):
    async def create(self, new: NewProceduralMemory) -> ProceduralMemoryRecord:
        """Insert a new active procedural memory. If an active row already
        exists for `(namespace, name)`, the new row supersedes it
        (`supersedes`/`superseded_by` linked on both sides, mirroring
        `relations`' soft-supersede mechanics, ADR 0004/FR9) rather than
        erroring or overwriting in place."""
        ...

    async def get_by_name(self, namespace: str, name: str) -> ProceduralMemoryRecord | None:
        """Return the currently-active (non-superseded, non-deleted) row for
        this name, or None."""
        ...

    async def search_hybrid(
        self,
        namespace: str,
        query_text: str,
        query_embedding: list[float] | None,
        kind: Literal["skill", "lesson", "all"],
        limit: int,
    ) -> list[ProceduralSearchResult]:
        """Hybrid text+vector search over active procedural memories,
        mirroring `MemoryRepository.search_hybrid`'s shape. `query_embedding
        is None` degrades to text-only ranking (mirrors graceful degradation
        elsewhere in this codebase when embedding is unavailable)."""
        ...

    async def record_outcome(
        self, namespace: str, name: str, success: bool, delta_alpha: float, delta_beta: float
    ) -> ProceduralMemoryRecord | None:
        """Atomically add `delta_alpha`/`delta_beta` to the active row's
        Beta belief, bump `applied_count`, and bump `success_count` when
        `success`. Returns the updated row, or None if no active row has
        this name (ADR 0024)."""
        ...

    async def link_provenance(self, procedural_memory_id: str, memory_id: str) -> None:
        """Idempotent, mirrors `GraphRepository.link_relation_provenance`."""
        ...

    async def get_provenance(self, namespace: str, procedural_memory_id: str) -> list[str]:
        """Source episode ids a procedural memory was distilled from."""
        ...
