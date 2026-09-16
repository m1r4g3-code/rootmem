"""Runs the same behavioral contract as the in-memory graph fake against a
real Postgres database, plus a direct-inspection verification that a
superseded relation is never deleted (ADR 0006/0008's extension of ADR
0004's soft-delete discipline to the graph layer).

Requires migrations applied (`uv run python scripts/migrate.py`) beforehand.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from tests.unit.storage.graph_contract import GraphRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    settings = get_settings()
    created_pool = await create_pool(settings)
    async with created_pool.acquire() as conn:
        await conn.execute("TRUNCATE relations, memory_entities, entities CASCADE")
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresGraphRepository(GraphRepositoryContract):
    @pytest.fixture
    def repository(self, pool: asyncpg.Pool) -> PostgresGraphRepository:
        return PostgresGraphRepository(pool, contradiction_confidence_floor=0.5)


@pytest.mark.asyncio
async def test_superseded_relation_row_still_physically_exists(pool: asyncpg.Pool) -> None:
    """Direct-inspection proof, mirroring test_postgres_roundtrip.py's
    test_soft_delete_preserves_row_and_sets_deleted_fields — the plan's exit
    criterion explicitly requires verifying this via direct SQL, not just the
    repository's own filtered read path."""
    repository = PostgresGraphRepository(pool, contradiction_confidence_floor=0.5)
    alice = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Person", name="Alice")
    )
    acme = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Acme")
    )
    globex = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Globex")
    )

    first = await repository.create_relation(
        NewRelation(
            namespace="ns",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=acme.id,
        )
    )
    await repository.create_relation(
        NewRelation(
            namespace="ns",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=globex.id,
        )
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT valid_to, superseded_by, object_entity_id FROM relations WHERE id = $1",
            first.new.id,
        )

    assert row is not None
    assert row["valid_to"] is not None
    assert row["superseded_by"] is not None
    assert str(row["object_entity_id"]) == acme.id


@pytest.mark.asyncio
async def test_link_memory_entity_is_idempotent(pool: asyncpg.Pool) -> None:
    """The Postgres-specific version of
    tests/unit/storage/test_in_memory_graph_repository.py's equivalent test
    — memory_entities.memory_id has a real foreign key to memories(id), so
    this needs an actual memory row, unlike the shared contract suite."""
    repository = PostgresGraphRepository(pool)
    entity = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Person", name="Alice")
    )

    async with pool.acquire() as conn:
        memory_id = await conn.fetchval(
            "INSERT INTO memories (namespace, content, source) "
            "VALUES ('ns', 'test memory', 'test') RETURNING id"
        )

    await repository.link_memory_entity(str(memory_id), entity.id)
    await repository.link_memory_entity(str(memory_id), entity.id)

    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM memory_entities WHERE memory_id = $1 AND entity_id = $2",
            memory_id,
            entity.id,
        )
    assert count == 1
