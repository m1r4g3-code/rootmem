"""Runs the same behavioral contract as the in-memory procedural-memory fake
against a real Postgres database, plus a provenance test using real inserted
`memories` rows (procedural_memory_provenance.memory_id has a real foreign
key, see procedural_contract.py's module docstring).

Requires migrations applied (`uv run python scripts/migrate.py`) beforehand.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.procedural_protocols import NewProceduralMemory
from tests.integration.db_guard import truncate
from tests.unit.storage.procedural_contract import ProceduralMemoryRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    settings = get_settings()
    created_pool = await create_pool(settings)
    async with created_pool.acquire() as conn:
        await truncate(conn, "procedural_memory_provenance, procedural_memories CASCADE")
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresProceduralMemoryRepository(ProceduralMemoryRepositoryContract):
    @pytest.fixture
    def repository(self, pool: asyncpg.Pool) -> PostgresProceduralMemoryRepository:
        return PostgresProceduralMemoryRepository(pool)


@pytest.mark.asyncio
async def test_link_provenance_is_idempotent_and_readable(pool: asyncpg.Pool) -> None:
    """The Postgres-specific version of
    test_in_memory_procedural_repository.py's equivalent test --
    procedural_memory_provenance.memory_id has a real foreign key to
    memories(id)."""
    repository = PostgresProceduralMemoryRepository(pool)
    record = await repository.create(
        NewProceduralMemory(
            namespace="ns", kind="skill", name="a-skill", description="d", body_markdown="b"
        )
    )

    async with pool.acquire() as conn:
        memory_id_1 = await conn.fetchval(
            "INSERT INTO memories (namespace, content, source) "
            "VALUES ('ns', 'first episode', 'test') RETURNING id"
        )
        memory_id_2 = await conn.fetchval(
            "INSERT INTO memories (namespace, content, source) "
            "VALUES ('ns', 'second episode', 'test') RETURNING id"
        )

    await repository.link_provenance(record.id, str(memory_id_1))
    await repository.link_provenance(record.id, str(memory_id_2))
    # Idempotent -- linking the same pair twice is a no-op.
    await repository.link_provenance(record.id, str(memory_id_1))

    provenance = await repository.get_provenance("ns", record.id)
    assert sorted(provenance) == sorted([str(memory_id_1), str(memory_id_2)])
