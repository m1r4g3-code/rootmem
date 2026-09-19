"""`asyncpg`-backed `MemoryRepository`. See ADR 0003 — this is the only
implementation besides `InMemoryMemoryRepository`, and both are verified
against the same contract-test suite for behavioral parity."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import asyncpg

from rootmem.storage.models import MemoryRecord, MemoryUpdate, NewMemory, SearchResult
from rootmem.storage.protocols import NotFoundError, StorageError

_SELECT_COLUMNS = (
    "id, schema_version, namespace, key, idempotency_key, content, content_embedding, "
    "source, source_session_id, confidence, importance_flag, salience_score, consolidated_at, "
    "session_outcome, last_accessed_at, access_count, metadata, created_at, updated_at, "
    "deleted_at, deleted_reason"
)


def _is_syntactically_valid_id(memory_id: str) -> bool:
    """`id` is a UUID column: a value that isn't even shaped like a UUID can
    never match a row, so callers should treat it as "not found" rather than
    let asyncpg's client-side parameter encoding raise a DataError that would
    otherwise surface as an opaque StorageError — the in-memory fake has no
    such format constraint, so this keeps both implementations' behavior
    identical for the same input (see the shared contract-test suite)."""
    try:
        uuid.UUID(memory_id)
    except ValueError:
        return False
    return True


def _row_to_record(row: asyncpg.Record) -> MemoryRecord:
    # pgvector's asyncpg codec (register_vector, see connection.py) decodes
    # a VECTOR column to its own Vector wrapper, not a plain list — .to_list()
    # is how it documents converting back to list[float].
    embedding = row["content_embedding"]
    return MemoryRecord(
        id=str(row["id"]),
        schema_version=row["schema_version"],
        namespace=row["namespace"],
        key=row["key"],
        idempotency_key=row["idempotency_key"],
        content=row["content"],
        content_embedding=embedding.to_list() if embedding is not None else None,
        source=row["source"],
        source_session_id=row["source_session_id"],
        confidence=row["confidence"],
        importance_flag=row["importance_flag"],
        salience_score=row["salience_score"],
        consolidated_at=row["consolidated_at"],
        session_outcome=row["session_outcome"],
        last_accessed_at=row["last_accessed_at"],
        access_count=row["access_count"],
        metadata=row["metadata"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        deleted_reason=row["deleted_reason"],
    )


class PostgresMemoryRepository:
    def __init__(
        self, pool: asyncpg.Pool, weight_text: float = 0.5, weight_vector: float = 0.5
    ) -> None:
        self._pool = pool
        self._weight_text = weight_text
        self._weight_vector = weight_vector

    async def create(self, memory: NewMemory) -> MemoryRecord:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO memories
                        (namespace, key, idempotency_key, content, content_embedding, source,
                         source_session_id, confidence, importance_flag, session_outcome, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (namespace, idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO NOTHING
                    RETURNING {_SELECT_COLUMNS}
                    """,
                    memory.namespace,
                    memory.key,
                    memory.idempotency_key,
                    memory.content,
                    memory.content_embedding,
                    memory.source,
                    memory.source_session_id,
                    memory.confidence,
                    memory.importance_flag,
                    memory.session_outcome,
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
        if not _is_syntactically_valid_id(memory_id):
            return None
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
        if not _is_syntactically_valid_id(memory_id):
            raise NotFoundError(f"memory {memory_id!r} not found")
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
        if not _is_syntactically_valid_id(memory_id):
            raise NotFoundError(f"memory {memory_id!r} not found")
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

    async def search_semantic(
        self,
        namespace: str,
        query_embedding: list[float],
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT {_SELECT_COLUMNS},
                           1 - (content_embedding <=> $2) AS score
                    FROM memories
                    WHERE namespace = $1
                      AND deleted_at IS NULL
                      AND content_embedding IS NOT NULL
                      AND ($4::text IS NULL OR source = $4)
                    ORDER BY score DESC
                    LIMIT $3
                    """,
                    namespace,
                    query_embedding,
                    limit,
                    source,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to semantic-search memories: {exc}") from exc
        return [SearchResult(record=_row_to_record(row), score=row["score"]) for row in rows]

    async def search_hybrid(
        self,
        namespace: str,
        query: str,
        query_embedding: list[float],
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT * FROM (
                        SELECT {_SELECT_COLUMNS},
                               $5 * COALESCE(
                                   ts_rank(
                                       to_tsvector('english', content),
                                       plainto_tsquery('english', $2)
                                   ),
                                   0
                               )
                               + $6 * COALESCE(
                                   CASE WHEN content_embedding IS NOT NULL
                                        THEN 1 - (content_embedding <=> $3) END,
                                   0
                               ) AS score
                        FROM memories
                        WHERE namespace = $1
                          AND deleted_at IS NULL
                          AND ($4::text IS NULL OR source = $4)
                    ) scored
                    -- Not `score > 0`: `ts_rank` can return a tiny nonzero
                    -- value (~1e-20) for a document with NO matching lexemes
                    -- at all -- a floating-point artifact of its internal
                    -- ranking arithmetic, found via direct reproduction
                    -- against this exact query shape while building Phase
                    -- 3's procedural-memory search (same pattern, same bug,
                    -- fixed here too since it's real and the fix is safe).
                    -- 1e-9 is comfortably below any genuine match's score
                    -- and comfortably above that noise floor.
                    WHERE score > 1e-9
                    ORDER BY score DESC
                    LIMIT $7
                    """,
                    namespace,
                    query,
                    query_embedding,
                    source,
                    self._weight_text,
                    self._weight_vector,
                    limit,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to hybrid-search memories: {exc}") from exc
        return [SearchResult(record=_row_to_record(row), score=row["score"]) for row in rows]

    async def count_unconsolidated(self, namespace: str) -> int:
        try:
            async with self._pool.acquire() as conn:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM memories
                    WHERE namespace = $1 AND deleted_at IS NULL AND consolidated_at IS NULL
                    """,
                    namespace,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to count unconsolidated memories: {exc}") from exc
        return int(count)

    async def list_unconsolidated(self, namespace: str, limit: int) -> list[MemoryRecord]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT {_SELECT_COLUMNS} FROM memories
                    WHERE namespace = $1 AND deleted_at IS NULL AND consolidated_at IS NULL
                    ORDER BY created_at
                    LIMIT $2
                    """,
                    namespace,
                    limit,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to list unconsolidated memories: {exc}") from exc
        return [_row_to_record(row) for row in rows]

    async def mark_consolidated(self, memory_ids: list[str], consolidated_at: datetime) -> None:
        if not memory_ids:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memories SET consolidated_at = $2 WHERE id = ANY($1::uuid[])",
                    memory_ids,
                    consolidated_at,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to mark memories consolidated: {exc}") from exc

    async def record_access(self, memory_ids: list[str], accessed_at: datetime) -> None:
        # Ids that aren't even UUID-shaped can never match; ignore them, as
        # the in-memory fake does, rather than fail the whole batch.
        memory_ids = [mid for mid in memory_ids if _is_syntactically_valid_id(mid)]
        if not memory_ids:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memories SET last_accessed_at = $2, access_count = access_count + 1 "
                    "WHERE id = ANY($1::uuid[]) AND deleted_at IS NULL",
                    memory_ids,
                    accessed_at,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to record access: {exc}") from exc

    async def update_salience(self, memory_id: str, salience_score: float) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memories SET salience_score = $2 WHERE id = $1",
                    memory_id,
                    salience_score,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to update salience: {exc}") from exc

    async def find_similar_pairs(
        self, namespace: str, memory_ids: list[str], threshold: float
    ) -> list[tuple[str, str, float]]:
        if not memory_ids:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT a.id AS id_a, b.id AS id_b,
                           1 - (a.content_embedding <=> b.content_embedding) AS similarity
                    FROM memories a
                    JOIN memories b ON a.id < b.id
                    WHERE a.namespace = $1 AND b.namespace = $1
                      AND a.id = ANY($2::uuid[]) AND b.id = ANY($2::uuid[])
                      AND a.content_embedding IS NOT NULL AND b.content_embedding IS NOT NULL
                      AND 1 - (a.content_embedding <=> b.content_embedding) >= $3
                    """,
                    namespace,
                    memory_ids,
                    threshold,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to find similar memory pairs: {exc}") from exc
        return [(str(row["id_a"]), str(row["id_b"]), row["similarity"]) for row in rows]
