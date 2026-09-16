"""`asyncpg`-backed `GraphRepository`. See ADR 0006 — the bi-temporal
semantic graph is plain Postgres tables (`entities`, `relations`,
`memory_entities`), not a dedicated graph engine, queried here via
recursive CTEs for traversal."""

from __future__ import annotations

import asyncpg

from rootmem.storage.graph_models import (
    ContradictionResolution,
    EntityRecord,
    NewEntity,
    NewRelation,
    RelationRecord,
)
from rootmem.storage.graph_normalize import normalize_entity_name
from rootmem.storage.protocols import StorageError

_ENTITY_COLUMNS = (
    "id, namespace, entity_type, name, canonical_key, attributes, created_at, updated_at"
)

_RELATION_COLUMNS = (
    "id, namespace, subject_entity_id, predicate, object_entity_id, object_literal, "
    "confidence, valid_from, valid_to, recorded_at, supersedes, superseded_by, "
    "source_memory_id, metadata"
)
_RELATION_COLUMNS_R_PREFIXED = ", ".join(f"r.{c.strip()}" for c in _RELATION_COLUMNS.split(","))


def _row_to_entity(row: asyncpg.Record) -> EntityRecord:
    return EntityRecord(
        id=str(row["id"]),
        namespace=row["namespace"],
        entity_type=row["entity_type"],
        name=row["name"],
        canonical_key=row["canonical_key"],
        attributes=row["attributes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_relation(row: asyncpg.Record) -> RelationRecord:
    return RelationRecord(
        id=str(row["id"]),
        namespace=row["namespace"],
        subject_entity_id=str(row["subject_entity_id"]),
        predicate=row["predicate"],
        object_entity_id=str(row["object_entity_id"]) if row["object_entity_id"] else None,
        object_literal=row["object_literal"],
        confidence=row["confidence"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        recorded_at=row["recorded_at"],
        supersedes=str(row["supersedes"]) if row["supersedes"] else None,
        superseded_by=str(row["superseded_by"]) if row["superseded_by"] else None,
        source_memory_id=str(row["source_memory_id"]) if row["source_memory_id"] else None,
        metadata=row["metadata"],
    )


class PostgresGraphRepository:
    def __init__(self, pool: asyncpg.Pool, contradiction_confidence_floor: float = 0.5) -> None:
        self._pool = pool
        self._contradiction_confidence_floor = contradiction_confidence_floor

    async def upsert_entity(self, entity: NewEntity) -> EntityRecord:
        canonical_key = normalize_entity_name(entity.name)
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO entities (namespace, entity_type, name, canonical_key, attributes)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (namespace, entity_type, canonical_key) DO NOTHING
                    RETURNING {_ENTITY_COLUMNS}
                    """,
                    entity.namespace,
                    entity.entity_type,
                    entity.name,
                    canonical_key,
                    entity.attributes,
                )
                if row is None:
                    row = await conn.fetchrow(
                        f"""
                        SELECT {_ENTITY_COLUMNS} FROM entities
                        WHERE namespace = $1 AND entity_type = $2 AND canonical_key = $3
                        """,
                        entity.namespace,
                        entity.entity_type,
                        canonical_key,
                    )
                if (
                    row is None
                ):  # pragma: no cover - defensive, mirrors PostgresMemoryRepository.create
                    raise StorageError(
                        "insert reported a conflict but no existing entity was found"
                    )
                return _row_to_entity(row)
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to upsert entity: {exc}") from exc

    async def get_entity_by_id(self, namespace: str, entity_id: str) -> EntityRecord | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT {_ENTITY_COLUMNS} FROM entities WHERE namespace = $1 AND id = $2",
                    namespace,
                    entity_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to get entity by id: {exc}") from exc
        return _row_to_entity(row) if row is not None else None

    async def find_entity_by_name(
        self, namespace: str, entity_type: str, name: str
    ) -> EntityRecord | None:
        canonical_key = normalize_entity_name(name)
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    SELECT {_ENTITY_COLUMNS} FROM entities
                    WHERE namespace = $1 AND entity_type = $2 AND canonical_key = $3
                    """,
                    namespace,
                    entity_type,
                    canonical_key,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to find entity by name: {exc}") from exc
        return _row_to_entity(row) if row is not None else None

    async def create_relation(self, relation: NewRelation) -> ContradictionResolution:
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                previous_row = await conn.fetchrow(
                    f"""
                    SELECT {_RELATION_COLUMNS} FROM relations
                    WHERE namespace = $1 AND subject_entity_id = $2 AND predicate = $3
                      AND valid_to IS NULL
                    FOR UPDATE
                    """,
                    relation.namespace,
                    relation.subject_entity_id,
                    relation.predicate,
                )
                previous = _row_to_relation(previous_row) if previous_row is not None else None
                contested = (
                    previous is not None
                    and relation.confidence <= self._contradiction_confidence_floor
                )

                new_metadata = dict(relation.metadata)
                if contested:
                    new_metadata["contested"] = True

                new_row = await conn.fetchrow(
                    f"""
                    INSERT INTO relations
                        (namespace, subject_entity_id, predicate, object_entity_id,
                         object_literal, confidence, supersedes, source_memory_id, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING {_RELATION_COLUMNS}
                    """,
                    relation.namespace,
                    relation.subject_entity_id,
                    relation.predicate,
                    relation.object_entity_id,
                    relation.object_literal,
                    relation.confidence,
                    previous.id if (previous is not None and not contested) else None,
                    relation.source_memory_id,
                    new_metadata,
                )
                assert new_row is not None
                new_record = _row_to_relation(new_row)

                if previous is not None:
                    if contested:
                        previous_metadata = dict(previous.metadata)
                        previous_metadata["contested"] = True
                        updated_previous_row = await conn.fetchrow(
                            f"""
                            UPDATE relations SET metadata = $2
                            WHERE id = $1
                            RETURNING {_RELATION_COLUMNS}
                            """,
                            previous.id,
                            previous_metadata,
                        )
                    else:
                        updated_previous_row = await conn.fetchrow(
                            f"""
                            UPDATE relations SET valid_to = $2, superseded_by = $3
                            WHERE id = $1
                            RETURNING {_RELATION_COLUMNS}
                            """,
                            previous.id,
                            new_record.valid_from,
                            new_record.id,
                        )
                    assert updated_previous_row is not None
                    previous = _row_to_relation(updated_previous_row)
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to create relation: {exc}") from exc

        return ContradictionResolution(new=new_record, previous=previous, contested=contested)

    async def get_relation_by_id(self, namespace: str, relation_id: str) -> RelationRecord | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT {_RELATION_COLUMNS} FROM relations WHERE namespace = $1 AND id = $2",
                    namespace,
                    relation_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to get relation by id: {exc}") from exc
        return _row_to_relation(row) if row is not None else None

    async def related(
        self, namespace: str, entity_id: str, max_hops: int = 1
    ) -> list[RelationRecord]:
        if max_hops < 1:
            return []
        # A relation is included iff at least one of its endpoints is a
        # frontier node reached at hop < max_hops — i.e. a node the BFS still
        # had budget left to expand from when it found this relation. This
        # is stricter than "either endpoint is anywhere within max_hops of
        # entity_id": a relation whose only connection to entity_id is
        # through a node at exactly hop == max_hops is one hop too far,
        # since that node was never itself expanded (matches
        # InMemoryGraphRepository.related's frontier-by-frontier walk).
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    WITH RECURSIVE reachable(entity_id, hop) AS (
                        VALUES ($2::uuid, 0)
                        UNION
                        SELECT
                            CASE WHEN r.subject_entity_id = reachable.entity_id
                                 THEN r.object_entity_id ELSE r.subject_entity_id END,
                            reachable.hop + 1
                        FROM relations r
                        JOIN reachable
                            ON r.subject_entity_id = reachable.entity_id
                            OR r.object_entity_id = reachable.entity_id
                        WHERE r.namespace = $1
                          AND reachable.hop < $3
                          AND r.object_entity_id IS NOT NULL
                    ),
                    min_hop AS (
                        SELECT entity_id, MIN(hop) AS hop FROM reachable GROUP BY entity_id
                    )
                    SELECT DISTINCT {_RELATION_COLUMNS_R_PREFIXED}
                    FROM relations r
                    WHERE r.namespace = $1
                      AND (
                        EXISTS (
                            SELECT 1 FROM min_hop mh
                            WHERE mh.entity_id = r.subject_entity_id AND mh.hop < $3
                        )
                        OR EXISTS (
                            SELECT 1 FROM min_hop mh
                            WHERE mh.entity_id = r.object_entity_id AND mh.hop < $3
                        )
                      )
                    ORDER BY r.recorded_at
                    """,
                    namespace,
                    entity_id,
                    max_hops,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to find related relations: {exc}") from exc
        return [_row_to_relation(row) for row in rows]

    async def link_memory_entity(self, memory_id: str, entity_id: str) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO memory_entities (memory_id, entity_id)
                    VALUES ($1, $2)
                    ON CONFLICT (memory_id, entity_id) DO NOTHING
                    """,
                    memory_id,
                    entity_id,
                )
        except (asyncpg.PostgresError, ValueError) as exc:
            raise StorageError(f"failed to link memory to entity: {exc}") from exc
