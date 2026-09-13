"""Runs the same behavioral contract as the in-memory fake against a real
Postgres database, plus Postgres-specific soft-delete verification.

Requires Docker (`docker compose up -d`) and migrations applied
(`uv run python scripts/migrate.py`) beforehand — see the plan's manual
validation checklist. CI runs both steps before this file (see
.github/workflows/ci.yml's "integration" job).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.models import NewMemory
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.repository import PostgresMemoryRepository
from tests.unit.storage.contract import MemoryRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    settings = get_settings()
    created_pool = await create_pool(settings)
    async with created_pool.acquire() as conn:
        await conn.execute("TRUNCATE memories")
    try:
        yield created_pool
    finally:
        await created_pool.close()


@pytest.fixture
def repository(pool: asyncpg.Pool) -> PostgresMemoryRepository:
    return PostgresMemoryRepository(pool)


class TestPostgresMemoryRepository(MemoryRepositoryContract):
    pass


@pytest.mark.asyncio
async def test_soft_delete_preserves_row_and_sets_deleted_fields(
    repository: PostgresMemoryRepository, pool: asyncpg.Pool
) -> None:
    """The plan's exit criterion explicitly requires verifying, via direct
    inspection (not just the repository's own filtered read path), that a
    'forgotten' row still physically exists with deleted_at/deleted_reason
    set — this is what distinguishes soft-delete from a hard DELETE (ADR 0004)."""
    created = await repository.create(
        NewMemory(namespace="ns", content="soft-deleted row", source="test")
    )
    await repository.soft_delete(created.id, reason="direct-inspection test")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT deleted_at, deleted_reason FROM memories WHERE id = $1", created.id
        )

    assert row is not None
    assert row["deleted_at"] is not None
    assert row["deleted_reason"] == "direct-inspection test"
