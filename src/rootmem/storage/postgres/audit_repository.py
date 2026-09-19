"""`asyncpg`-backed `AuditLogRepository` (ADR 0025), backed by `audit_log`
(migration 0007). The table's trigger rejects UPDATE/DELETE, so this class
only ever inserts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from rootmem.audit.chain import GENESIS_HASH, AuditEntry, compute_hash
from rootmem.storage.protocols import StorageError

_COLUMNS = (
    "namespace, seq, actor, action, target_type, target_id, payload, created_at, "
    "prev_hash, row_hash"
)


def _row_to_entry(row: asyncpg.Record) -> AuditEntry:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return AuditEntry(
        namespace=row["namespace"],
        seq=row["seq"],
        actor=row["actor"],
        action=row["action"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        payload=payload,
        created_at=row["created_at"],
        prev_hash=row["prev_hash"],
        row_hash=row["row_hash"],
    )


class PostgresAuditLogRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        namespace: str,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None,
        payload: dict[str, Any],
        created_at: datetime | None = None,
    ) -> AuditEntry:
        stamp = created_at if created_at is not None else datetime.now(UTC)
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                # Serialize appends per namespace so two writers cannot both
                # read the same tail and fork the chain.
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", namespace)
                tail = await conn.fetchrow(
                    "SELECT seq, row_hash FROM audit_log WHERE namespace = $1 "
                    "ORDER BY seq DESC LIMIT 1",
                    namespace,
                )
                prev_hash = tail["row_hash"] if tail is not None else GENESIS_HASH
                seq = (tail["seq"] if tail is not None else 0) + 1
                row_hash = compute_hash(
                    prev_hash, namespace, seq, actor, action, target_type, target_id, payload, stamp
                )
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO audit_log ({_COLUMNS})
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
                    RETURNING {_COLUMNS}
                    """,
                    namespace,
                    seq,
                    actor,
                    action,
                    target_type,
                    target_id,
                    json.dumps(payload, default=str),
                    stamp,
                    prev_hash,
                    row_hash,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to append audit entry: {exc}") from exc
        assert row is not None
        return _row_to_entry(row)

    async def list_entries(self, namespace: str) -> list[AuditEntry]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT {_COLUMNS} FROM audit_log WHERE namespace = $1 ORDER BY seq",
                    namespace,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to list audit entries: {exc}") from exc
        return [_row_to_entry(row) for row in rows]
