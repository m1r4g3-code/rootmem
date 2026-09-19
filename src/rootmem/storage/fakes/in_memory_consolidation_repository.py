"""Dict-backed `ConsolidationRepository` fake — zero I/O, used by all unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from rootmem.storage.consolidation_protocols import ConsolidationRun
from rootmem.storage.protocols import NotFoundError


class InMemoryConsolidationRepository:
    def __init__(self) -> None:
        self._runs: dict[str, ConsolidationRun] = {}

    async def start_run(
        self, namespace: str, trigger_reason: Literal["count", "time", "manual"]
    ) -> ConsolidationRun:
        run = ConsolidationRun(
            id=str(uuid.uuid4()),
            namespace=namespace,
            trigger_reason=trigger_reason,
            started_at=datetime.now(UTC),
        )
        self._runs[run.id] = run
        return run

    async def complete_run(
        self,
        run_id: str,
        episodes_processed: int,
        clusters_formed: int,
        facts_distilled: int,
        procedures_distilled: int = 0,
        lessons_distilled: int = 0,
    ) -> ConsolidationRun:
        run = self._runs.get(run_id)
        if run is None:
            raise NotFoundError(f"consolidation run {run_id!r} not found")
        updated = run.model_copy(
            update={
                "completed_at": datetime.now(UTC),
                "episodes_processed": episodes_processed,
                "clusters_formed": clusters_formed,
                "facts_distilled": facts_distilled,
                "procedures_distilled": procedures_distilled,
                "lessons_distilled": lessons_distilled,
            }
        )
        self._runs[run_id] = updated
        return updated

    async def get_last_run(self, namespace: str) -> ConsolidationRun | None:
        candidates = [run for run in self._runs.values() if run.namespace == namespace]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.started_at)
