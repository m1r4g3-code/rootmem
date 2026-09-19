"""Runs the same behavioral contract as the in-memory consolidation fake
against a real Postgres database.

Requires migrations applied (`uv run python scripts/migrate.py`) beforehand.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.consolidation_repository import PostgresConsolidationRepository
from tests.integration.db_guard import truncate
from tests.unit.storage.consolidation_contract import ConsolidationRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    settings = get_settings()
    created_pool = await create_pool(settings)
    async with created_pool.acquire() as conn:
        await truncate(conn, "consolidation_runs")
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresConsolidationRepository(ConsolidationRepositoryContract):
    @pytest.fixture
    def repository(self, pool: asyncpg.Pool) -> PostgresConsolidationRepository:
        return PostgresConsolidationRepository(pool)
