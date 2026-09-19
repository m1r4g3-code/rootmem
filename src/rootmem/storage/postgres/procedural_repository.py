"""`asyncpg`-backed `ProceduralMemoryRepository`. See ADR 0017 — a distilled
skill/lesson artifact is its own aggregate, backed by the
`procedural_memories` table (migration 0005)."""

from __future__ import annotations

import uuid
from typing import Literal

import asyncpg

from rootmem.storage.procedural_protocols import (
    NewProceduralMemory,
    ProceduralMemoryRecord,
    ProceduralSearchResult,
)
from rootmem.storage.protocols import StorageError

_COLUMNS = (
    "id, namespace, kind, name, description, body_markdown, content_embedding, "
    "derivation, supersedes, superseded_by, created_at, updated_at, deleted_at, deleted_reason"
)


def _row_to_record(row: asyncpg.Record) -> ProceduralMemoryRecord:
    embedding = row["content_embedding"]
    return ProceduralMemoryRecord(
        id=str(row["id"]),
        namespace=row["namespace"],
        kind=row["kind"],
        name=row["name"],
        description=row["description"],
        body_markdown=row["body_markdown"],
        content_embedding=embedding.to_list() if embedding is not None else None,
        derivation=row["derivation"],
        supersedes=str(row["supersedes"]) if row["supersedes"] else None,
        superseded_by=str(row["superseded_by"]) if row["superseded_by"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
        deleted_reason=row["deleted_reason"],
    )


class PostgresProceduralMemoryRepository:
    def __init__(
        self, pool: asyncpg.Pool, weight_text: float = 0.5, weight_vector: float = 0.5
    ) -> None:
        self._pool = pool
        self._weight_text = weight_text
        self._weight_vector = weight_vector

    async def create(self, new: NewProceduralMemory) -> ProceduralMemoryRecord:
        # The new row's id is generated client-side (rather than left to
        # `DEFAULT gen_random_uuid()`) so the previous active row can be
        # marked superseded -- and therefore drop out of
        # ix_procedural_memories_active_name's partial-unique membership --
        # BEFORE the new row is inserted. Inserting first would transiently
        # violate that unique index, since Postgres checks it immediately,
        # not at commit (confirmed by a real UniqueViolationError from this
        # exact ordering during Phase 3's real-Postgres integration testing).
        new_id = str(uuid.uuid4())
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    previous = await conn.fetchrow(
                        f"""
                        SELECT {_COLUMNS} FROM procedural_memories
                        WHERE namespace = $1 AND name = $2
                          AND superseded_by IS NULL AND deleted_at IS NULL
                        FOR UPDATE
                        """,
                        new.namespace,
                        new.name,
                    )
                    if previous is not None:
                        await conn.execute(
                            "UPDATE procedural_memories SET superseded_by = $2, "
                            "updated_at = now() WHERE id = $1",
                            previous["id"],
                            new_id,
                        )
                    row = await conn.fetchrow(
                        f"""
                        INSERT INTO procedural_memories
                            (id, namespace, kind, name, description, body_markdown,
                             content_embedding, supersedes)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        RETURNING {_COLUMNS}
                        """,
                        new_id,
                        new.namespace,
                        new.kind,
                        new.name,
                        new.description,
                        new.body_markdown,
                        new.content_embedding,
                        previous["id"] if previous is not None else None,
                    )
                    assert row is not None
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to create procedural memory: {exc}") from exc
        return _row_to_record(row)

    async def get_by_name(self, namespace: str, name: str) -> ProceduralMemoryRecord | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_COLUMNS} FROM procedural_memories
                    WHERE namespace = $1 AND name = $2
                      AND superseded_by IS NULL AND deleted_at IS NULL
                    """,
                    namespace,
                    name,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to get procedural memory by name: {exc}") from exc
        return _row_to_record(row) if row is not None else None

    async def search_hybrid(
        self,
        namespace: str,
        query_text: str,
        query_embedding: list[float] | None,
        kind: Literal["skill", "lesson", "all"],
        limit: int,
    ) -> list[ProceduralSearchResult]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT * FROM (
                        SELECT {_COLUMNS},
                               $6 * COALESCE(
                                   ts_rank(
                                       to_tsvector(
                                           'english',
                                           name || ' ' || description || ' ' || body_markdown
                                       ),
                                       plainto_tsquery('english', $2)
                                   ),
                                   0
                               )
                               + $7 * COALESCE(
                                   CASE
                                       WHEN $3::vector IS NOT NULL AND content_embedding IS NOT NULL
                                       THEN 1 - (content_embedding <=> $3::vector)
                                   END,
                                   0
                               ) AS score
                        FROM procedural_memories
                        WHERE namespace = $1
                          AND superseded_by IS NULL AND deleted_at IS NULL
                          AND ($4::text IS NULL OR kind = $4)
                    ) scored
                    -- Not `score > 0`: a real run against this exact table
                    -- showed `ts_rank` can return a tiny nonzero value
                    -- (~1e-20) for a document with NO matching lexemes at
                    -- all -- a known floating-point artifact of its internal
                    -- ranking arithmetic, confirmed by direct reproduction
                    -- during Phase 3's integration testing (not a hypothetical).
                    -- 1e-9 is comfortably below any genuine match's score
                    -- (text/vector contributions are both O(0.1) or larger)
                    -- and comfortably above that noise floor.
                    WHERE score > 1e-9
                    ORDER BY score DESC
                    LIMIT $5
                    """,
                    namespace,
                    query_text,
                    query_embedding,
                    None if kind == "all" else kind,
                    limit,
                    self._weight_text,
                    self._weight_vector,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to hybrid-search procedural memories: {exc}") from exc
        return [
            ProceduralSearchResult(record=_row_to_record(row), score=row["score"]) for row in rows
        ]

    async def link_provenance(self, procedural_memory_id: str, memory_id: str) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO procedural_memory_provenance (procedural_memory_id, memory_id)
                    VALUES ($1, $2)
                    ON CONFLICT (procedural_memory_id, memory_id) DO NOTHING
                    """,
                    procedural_memory_id,
                    memory_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to link procedural memory provenance: {exc}") from exc

    async def get_provenance(self, namespace: str, procedural_memory_id: str) -> list[str]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT pmp.memory_id FROM procedural_memory_provenance pmp
                    JOIN procedural_memories pm ON pm.id = pmp.procedural_memory_id
                    WHERE pm.namespace = $1 AND pmp.procedural_memory_id = $2
                    """,
                    namespace,
                    procedural_memory_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to get procedural memory provenance: {exc}") from exc
        return [str(row["memory_id"]) for row in rows]
