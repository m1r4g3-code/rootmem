"""The consolidation storage port: `ConsolidationRepository`.

A new, separate Protocol from `MemoryRepository` and `GraphRepository` (ADR
0016) — a consolidation run is neither a memory nor a relation, it's a
record of when the system did background work, the same "genuinely
different aggregate" test ADR 0006 already used to justify `GraphRepository`
being separate from `MemoryRepository`. `InMemoryConsolidationRepository`
and `PostgresConsolidationRepository` both satisfy it and are verified
against the same contract-test suite
(`tests/unit/storage/consolidation_contract.py`) for behavioral parity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class ConsolidationRun(BaseModel):
    """One consolidation pass's record — created when a pass starts,
    completed when it finishes. `completed_at is None` means the run is
    still in progress (or crashed mid-run, in the case of a background
    inline-triggered pass that never got to call `complete_run`)."""

    model_config = ConfigDict(frozen=True)

    id: str
    namespace: str
    trigger_reason: Literal["count", "time", "manual"]
    started_at: datetime
    completed_at: datetime | None = None
    episodes_processed: int = 0
    clusters_formed: int = 0
    facts_distilled: int = 0


class ConsolidationRepository(Protocol):
    async def start_run(
        self, namespace: str, trigger_reason: Literal["count", "time", "manual"]
    ) -> ConsolidationRun:
        """Record the start of a consolidation pass."""
        ...

    async def complete_run(
        self,
        run_id: str,
        episodes_processed: int,
        clusters_formed: int,
        facts_distilled: int,
    ) -> ConsolidationRun:
        """Record a pass's completion and its outcome counts."""
        ...

    async def get_last_run(self, namespace: str) -> ConsolidationRun | None:
        """Return the most recently *started* run for this namespace (by
        `started_at`), or None if consolidation has never run for it —
        `consolidation.trigger.should_consolidate` (ADR 0016) treats a
        namespace with no prior run as always eligible for the time-based
        trigger."""
        ...
