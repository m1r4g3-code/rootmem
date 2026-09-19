"""`asyncpg`-backed `PortabilityRepository` (ADR 0037).

Export runs in one read-only, repeatable-read transaction so the bundle is a
consistent snapshot. Import runs in one transaction with fresh ids: either
every record lands or none does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg

from rootmem.portability.bundle import Bundle, BundleRecord, build_bundle
from rootmem.storage.graph_normalize import normalize_entity_name, normalize_entity_type
from rootmem.storage.portability_protocols import NamespaceNotEmptyError
from rootmem.storage.protocols import StorageError


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _uid(mapping: dict[str, str], source_id: str | None) -> str | None:
    return mapping.get(source_id) if source_id else None


class PostgresPortabilityRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def export_namespace(self, namespace: str) -> Bundle:
        records: list[BundleRecord] = []
        try:
            async with (
                self._pool.acquire() as conn,
                conn.transaction(isolation="repeatable_read", readonly=True),
            ):
                for row in await conn.fetch(
                    """
                    SELECT id, key, content, source, source_session_id, confidence,
                           importance_flag, salience_score, consolidated_at, session_outcome,
                           last_accessed_at, access_count, metadata, created_at
                    FROM memories WHERE namespace = $1 AND deleted_at IS NULL
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="memory",
                            data={
                                "id": str(row["id"]),
                                "key": row["key"],
                                "content": row["content"],
                                "source": row["source"],
                                "source_session_id": row["source_session_id"],
                                "confidence": row["confidence"],
                                "importance_flag": row["importance_flag"],
                                "salience_score": row["salience_score"],
                                "consolidated_at": _iso(row["consolidated_at"]),
                                "session_outcome": row["session_outcome"],
                                "last_accessed_at": _iso(row["last_accessed_at"]),
                                "access_count": row["access_count"],
                                "metadata": row["metadata"],
                                "created_at": _iso(row["created_at"]),
                            },
                        )
                    )
                for row in await conn.fetch(
                    "SELECT id, entity_type, name, attributes, created_at "
                    "FROM entities WHERE namespace = $1",
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="entity",
                            data={
                                "id": str(row["id"]),
                                "entity_type": row["entity_type"],
                                "name": row["name"],
                                "attributes": row["attributes"],
                                "created_at": _iso(row["created_at"]),
                            },
                        )
                    )
                for row in await conn.fetch(
                    """
                    SELECT id, subject_entity_id, predicate, object_entity_id, object_literal,
                           confidence, belief_alpha, belief_beta, valid_from, valid_to,
                           recorded_at, supersedes, superseded_by, derivation,
                           source_memory_id, metadata
                    FROM relations WHERE namespace = $1
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="relation",
                            data={
                                "id": str(row["id"]),
                                "subject_entity_id": str(row["subject_entity_id"]),
                                "predicate": row["predicate"],
                                "object_entity_id": (
                                    str(row["object_entity_id"])
                                    if row["object_entity_id"]
                                    else None
                                ),
                                "object_literal": row["object_literal"],
                                "confidence": row["confidence"],
                                "belief_alpha": row["belief_alpha"],
                                "belief_beta": row["belief_beta"],
                                "valid_from": _iso(row["valid_from"]),
                                "valid_to": _iso(row["valid_to"]),
                                "recorded_at": _iso(row["recorded_at"]),
                                "supersedes": str(row["supersedes"]) if row["supersedes"] else None,
                                "superseded_by": (
                                    str(row["superseded_by"]) if row["superseded_by"] else None
                                ),
                                "derivation": row["derivation"],
                                "source_memory_id": (
                                    str(row["source_memory_id"])
                                    if row["source_memory_id"]
                                    else None
                                ),
                                "metadata": row["metadata"],
                            },
                        )
                    )
                for row in await conn.fetch(
                    """
                    SELECT me.memory_id, me.entity_id
                    FROM memory_entities me
                    JOIN memories m ON m.id = me.memory_id
                    JOIN entities e ON e.id = me.entity_id
                    WHERE m.namespace = $1 AND m.deleted_at IS NULL AND e.namespace = $1
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="memory_entity",
                            data={
                                "memory_id": str(row["memory_id"]),
                                "entity_id": str(row["entity_id"]),
                            },
                        )
                    )
                for row in await conn.fetch(
                    """
                    SELECT rp.relation_id, rp.memory_id
                    FROM relation_provenance rp
                    JOIN relations r ON r.id = rp.relation_id
                    JOIN memories m ON m.id = rp.memory_id
                    WHERE r.namespace = $1 AND m.namespace = $1 AND m.deleted_at IS NULL
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="relation_provenance",
                            data={
                                "relation_id": str(row["relation_id"]),
                                "memory_id": str(row["memory_id"]),
                            },
                        )
                    )
                for row in await conn.fetch(
                    """
                    SELECT id, kind, name, description, body_markdown, derivation,
                           belief_alpha, belief_beta, applied_count, success_count, created_at
                    FROM procedural_memories
                    WHERE namespace = $1 AND superseded_by IS NULL AND deleted_at IS NULL
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="skill",
                            data={
                                "id": str(row["id"]),
                                "kind": row["kind"],
                                "name": row["name"],
                                "description": row["description"],
                                "body_markdown": row["body_markdown"],
                                "derivation": row["derivation"],
                                "belief_alpha": row["belief_alpha"],
                                "belief_beta": row["belief_beta"],
                                "applied_count": row["applied_count"],
                                "success_count": row["success_count"],
                                "created_at": _iso(row["created_at"]),
                            },
                        )
                    )
                for row in await conn.fetch(
                    """
                    SELECT pp.procedural_memory_id, pp.memory_id
                    FROM procedural_memory_provenance pp
                    JOIN procedural_memories p ON p.id = pp.procedural_memory_id
                    JOIN memories m ON m.id = pp.memory_id
                    WHERE p.namespace = $1 AND p.superseded_by IS NULL AND p.deleted_at IS NULL
                      AND m.namespace = $1 AND m.deleted_at IS NULL
                    """,
                    namespace,
                ):
                    records.append(
                        BundleRecord(
                            kind="skill_provenance",
                            data={
                                "procedural_memory_id": str(row["procedural_memory_id"]),
                                "memory_id": str(row["memory_id"]),
                            },
                        )
                    )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to export namespace: {exc}") from exc
        return build_bundle(namespace, records, datetime.now(UTC))

    async def import_bundle(self, target_namespace: str, bundle: Bundle) -> dict[str, int]:
        now = datetime.now(UTC)
        counts = {kind: 0 for kind in bundle.manifest.counts}
        memory_ids: dict[str, str] = {}
        entity_ids: dict[str, str] = {}
        relation_ids: dict[str, str] = {}
        skill_ids: dict[str, str] = {}
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                occupied = await conn.fetchval(
                    """
                    SELECT EXISTS (SELECT 1 FROM memories WHERE namespace = $1)
                        OR EXISTS (SELECT 1 FROM entities WHERE namespace = $1)
                        OR EXISTS (SELECT 1 FROM procedural_memories WHERE namespace = $1)
                    """,
                    target_namespace,
                )
                if occupied:
                    raise NamespaceNotEmptyError(target_namespace)

                for d in bundle.of_kind("memory"):
                    new_id = str(uuid.uuid4())
                    memory_ids[d["id"]] = new_id
                    created = _dt(d["created_at"]) or now
                    await conn.execute(
                        """
                        INSERT INTO memories (
                            id, namespace, key, content, source, source_session_id, confidence,
                            importance_flag, salience_score, consolidated_at, session_outcome,
                            last_accessed_at, access_count, metadata, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$15)
                        """,
                        new_id,
                        target_namespace,
                        d["key"],
                        d["content"],
                        d["source"],
                        d["source_session_id"],
                        d["confidence"],
                        d["importance_flag"],
                        d["salience_score"],
                        _dt(d["consolidated_at"]),
                        d["session_outcome"],
                        _dt(d["last_accessed_at"]),
                        d["access_count"],
                        d["metadata"],
                        created,
                    )
                    counts["memory"] += 1
                for d in bundle.of_kind("entity"):
                    new_id = str(uuid.uuid4())
                    entity_ids[d["id"]] = new_id
                    created = _dt(d["created_at"]) or now
                    await conn.execute(
                        """
                        INSERT INTO entities (id, namespace, entity_type, name, canonical_key,
                                              attributes, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$7)
                        """,
                        new_id,
                        target_namespace,
                        normalize_entity_type(d["entity_type"]),
                        d["name"],
                        normalize_entity_name(d["name"]),
                        d["attributes"],
                        created,
                    )
                    counts["entity"] += 1
                for d in bundle.of_kind("relation"):
                    new_id = str(uuid.uuid4())
                    relation_ids[d["id"]] = new_id
                    await conn.execute(
                        """
                        INSERT INTO relations (
                            id, namespace, subject_entity_id, predicate, object_entity_id,
                            object_literal, confidence, belief_alpha, belief_beta, valid_from,
                            valid_to, recorded_at, derivation, source_memory_id, metadata)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                        """,
                        new_id,
                        target_namespace,
                        entity_ids[d["subject_entity_id"]],
                        d["predicate"],
                        _uid(entity_ids, d["object_entity_id"]),
                        d["object_literal"],
                        d["confidence"],
                        d["belief_alpha"],
                        d["belief_beta"],
                        _dt(d["valid_from"]) or now,
                        _dt(d["valid_to"]),
                        _dt(d["recorded_at"]) or now,
                        d["derivation"],
                        _uid(memory_ids, d["source_memory_id"]),
                        d["metadata"],
                    )
                    counts["relation"] += 1
                # Supersede links point at other relations, so they are set
                # once every relation exists.
                for d in bundle.of_kind("relation"):
                    if d["supersedes"] or d["superseded_by"]:
                        await conn.execute(
                            "UPDATE relations SET supersedes = $2, superseded_by = $3 "
                            "WHERE id = $1",
                            relation_ids[d["id"]],
                            _uid(relation_ids, d["supersedes"]),
                            _uid(relation_ids, d["superseded_by"]),
                        )
                for d in bundle.of_kind("memory_entity"):
                    await conn.execute(
                        "INSERT INTO memory_entities (memory_id, entity_id) VALUES ($1, $2)",
                        memory_ids[d["memory_id"]],
                        entity_ids[d["entity_id"]],
                    )
                    counts["memory_entity"] += 1
                for d in bundle.of_kind("relation_provenance"):
                    await conn.execute(
                        "INSERT INTO relation_provenance (relation_id, memory_id) VALUES ($1, $2)",
                        relation_ids[d["relation_id"]],
                        memory_ids[d["memory_id"]],
                    )
                    counts["relation_provenance"] += 1
                for d in bundle.of_kind("skill"):
                    new_id = str(uuid.uuid4())
                    skill_ids[d["id"]] = new_id
                    created = _dt(d["created_at"]) or now
                    await conn.execute(
                        """
                        INSERT INTO procedural_memories (
                            id, namespace, kind, name, description, body_markdown, derivation,
                            belief_alpha, belief_beta, applied_count, success_count,
                            created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$12)
                        """,
                        new_id,
                        target_namespace,
                        d["kind"],
                        d["name"],
                        d["description"],
                        d["body_markdown"],
                        d["derivation"],
                        d["belief_alpha"],
                        d["belief_beta"],
                        d["applied_count"],
                        d["success_count"],
                        created,
                    )
                    counts["skill"] += 1
                for d in bundle.of_kind("skill_provenance"):
                    await conn.execute(
                        "INSERT INTO procedural_memory_provenance "
                        "(procedural_memory_id, memory_id) VALUES ($1, $2)",
                        skill_ids[d["procedural_memory_id"]],
                        memory_ids[d["memory_id"]],
                    )
                    counts["skill_provenance"] += 1
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to import bundle: {exc}") from exc
        return counts
