"""`asyncpg`-backed `ConsolidationRepository`. See ADR 0016 — a consolidation
run is its own aggregate, backed by the `consolidation_runs` table
(migration 0004)."""

from __future__ import annotations

from typing import Literal

import asyncpg

from rootmem.storage.consolidation_protocols import ConsolidationRun
from rootmem.storage.protocols import NotFoundError, StorageError

_RUN_COLUMNS = (
    "id, namespace, trigger_reason, started_at, completed_at, "
    "episodes_processed, clusters_formed, facts_distilled"
)


def _row_to_run(row: asyncpg.Record) -> ConsolidationRun:
    return ConsolidationRun(
        id=str(row["id"]),
        namespace=row["namespace"],
        trigger_reason=row["trigger_reason"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        episodes_processed=row["episodes_processed"],
        clusters_formed=row["clusters_formed"],
        facts_distilled=row["facts_distilled"],
    )


class PostgresConsolidationRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def start_run(
        self, namespace: str, trigger_reason: Literal["count", "time", "manual"]
    ) -> ConsolidationRun:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO consolidation_runs (namespace, trigger_reason)
                    VALUES ($1, $2)
                    RETURNING {_RUN_COLUMNS}
                    """,
                    namespace,
                    trigger_reason,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to start consolidation run: {exc}") from exc
        assert row is not None
        return _row_to_run(row)

    async def complete_run(
        self,
        run_id: str,
        episodes_processed: int,
        clusters_formed: int,
        facts_distilled: int,
    ) -> ConsolidationRun:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    UPDATE consolidation_runs
                    SET completed_at = now(), episodes_processed = $2,
                        clusters_formed = $3, facts_distilled = $4
                    WHERE id = $1
                    RETURNING {_RUN_COLUMNS}
                    """,
                    run_id,
                    episodes_processed,
                    clusters_formed,
                    facts_distilled,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to complete consolidation run: {exc}") from exc
        if row is None:
            raise NotFoundError(f"consolidation run {run_id!r} not found")
        return _row_to_run(row)

    async def get_last_run(self, namespace: str) -> ConsolidationRun | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_RUN_COLUMNS} FROM consolidation_runs
                    WHERE namespace = $1
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    namespace,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to get last consolidation run: {exc}") from exc
        return _row_to_run(row) if row is not None else None
