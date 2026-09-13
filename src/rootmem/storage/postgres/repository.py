"""`asyncpg`-backed `MemoryRepository`. See ADR 0003 — this is the only
implementation besides `InMemoryMemoryRepository`, and both are verified
against the same contract-test suite for behavioral parity."""

from __future__ import annotations

from typing import Any

import asyncpg

from rootmem.storage.models import MemoryRecord, MemoryUpdate, NewMemory, SearchResult
from rootmem.storage.protocols import NotFoundError, StorageError

_SELECT_COLUMNS = (
    "id, schema_version, namespace, key, idempotency_key, content, source, "
    "source_session_id, confidence, metadata, created_at, updated_at, "
    "deleted_at, deleted_reason"
)


def _row_to_record(row: asyncpg.Record) -> MemoryRecord:
    return MemoryRecord(
        id=str(row["id"]),
        schema_version=row["schema_version"],
        namespace=row["namespace"],
        key=row["key"],
        idempotency_key=row["idempotency_key"],
        content=row["content"],
        source=row["source"],
        source_session_id=row["source_session_id"],
        confidence=row["confidence"],
        metadata=row["metadata"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        deleted_reason=row["deleted_reason"],
    )


class PostgresMemoryRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, memory: NewMemory) -> MemoryRecord:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO memories
                        (namespace, key, idempotency_key, content, source,
                         source_session_id, confidence, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (namespace, idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    memory.namespace,
                    memory.key,
                    memory.idempotency_key,
                    memory.content,
                    memory.source,
                    memory.source_session_id,
                    memory.confidence,
                    memory.metadata,
                )
                if row is None:
                    # Idempotency-key collision: ON CONFLICT DO NOTHING inserted
                    # nothing, so the existing active record is the right return value.
                    row = await conn.fetchrow(
                        f"""
                        SELECT {_SELECT_COLUMNS} FROM memories
                        WHERE namespace = $1 AND idempotency_key = $2 AND deleted_at IS NULL
                        """,
                        memory.namespace,
                        memory.idempotency_key,
                    )
                if row is None:  # pragma: no cover - defensive, see module docstring
                    raise StorageError("insert reported a conflict but no existing row was found")
                return _row_to_record(row)
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to create memory: {exc}") from exc

    async def get_by_id(self, namespace: str, memory_id: str) -> MemoryRecord | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_SELECT_COLUMNS} FROM memories
                    WHERE namespace = $1 AND id = $2 AND deleted_at IS NULL
                    """,
                    namespace,
                    memory_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to get memory by id: {exc}") from exc
        return _row_to_record(row) if row is not None else None

    async def get_by_key(self, namespace: str, key: str) -> MemoryRecord | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_SELECT_COLUMNS} FROM memories
                    WHERE namespace = $1 AND key = $2 AND deleted_at IS NULL
                    """,
                    namespace,
                    key,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to get memory by key: {exc}") from exc
        return _row_to_record(row) if row is not None else None

    async def update(self, memory_id: str, changes: MemoryUpdate) -> MemoryRecord:
        fields: list[str] = []
        values: list[Any] = []
        if changes.content is not None:
            values.append(changes.content)
            fields.append(f"content = ${len(values)}")
        if changes.confidence is not None:
            values.append(changes.confidence)
            fields.append(f"confidence = ${len(values)}")
        if changes.metadata is not None:
            values.append(changes.metadata)
            fields.append(f"metadata = ${len(values)}")

        values.append(memory_id)
        set_clause = ", ".join(fields)
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    UPDATE memories SET {set_clause}
                    WHERE id = ${len(values)} AND deleted_at IS NULL
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    *values,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to update memory: {exc}") from exc
        if row is None:
            raise NotFoundError(f"memory {memory_id!r} not found")
        return _row_to_record(row)

    async def soft_delete(self, memory_id: str, reason: str | None) -> MemoryRecord:
        try:
            async with self._pool.acquire() as conn:
                existing = await conn.fetchrow(
                    f"SELECT {_SELECT_COLUMNS} FROM memories WHERE id = $1", memory_id
                )
                if existing is None:
                    raise NotFoundError(f"memory {memory_id!r} not found")
                if existing["deleted_at"] is not None:
                    return _row_to_record(existing)

                row = await conn.fetchrow(
                    f"""
                    UPDATE memories
                    SET deleted_at = now(), deleted_reason = $2
                    WHERE id = $1
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    memory_id,
                    reason,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to soft-delete memory: {exc}") from exc
        assert row is not None
        return _row_to_record(row)

    async def search_text(
        self,
        namespace: str,
        query: str,
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT {_SELECT_COLUMNS},
                           ts_rank(
                               to_tsvector('english', content), plainto_tsquery('english', $2)
                           ) AS score
                    FROM memories
                    WHERE namespace = $1
                      AND deleted_at IS NULL
                      AND to_tsvector('english', content) @@ plainto_tsquery('english', $2)
                      AND ($4::text IS NULL OR source = $4)
                    ORDER BY score DESC
                    LIMIT $3
                    """,
                    namespace,
                    query,
                    limit,
                    source,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to search memories: {exc}") from exc
        return [SearchResult(record=_row_to_record(row), score=row["score"]) for row in rows]
