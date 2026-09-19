"""Runs the portability contract against real Postgres (ADR 0037), where the
foreign keys, the partial unique index on active skill names and the
supersede-link ordering are real constraints the fake cannot exercise."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.portability_repository import PostgresPortabilityRepository
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.postgres.repository import PostgresMemoryRepository
from tests.unit.storage.portability_contract import PortabilityEnv, PortabilityRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    created_pool = await create_pool(get_settings())
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresPortabilityRepository(PortabilityRepositoryContract):
    @pytest.fixture
    def env(self, pool: asyncpg.Pool) -> PortabilityEnv:
        return PortabilityEnv(
            portability=PostgresPortabilityRepository(pool),
            memories=PostgresMemoryRepository(pool),
            graph=PostgresGraphRepository(pool),
            skills=PostgresProceduralMemoryRepository(pool),
        )
