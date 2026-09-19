"""Runs the identity contract against real Postgres (migration 0009)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository
from tests.unit.storage.identity_contract import IdentityRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    created_pool = await create_pool(get_settings())
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresIdentityRepository(IdentityRepositoryContract):
    @pytest.fixture
    def repository(self, pool: asyncpg.Pool) -> PostgresIdentityRepository:
        return PostgresIdentityRepository(pool)
