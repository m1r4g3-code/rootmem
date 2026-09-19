"""Runs the audit-log contract against real Postgres, plus the DB-level
append-only guarantee. Requires migration 0007 applied."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from rootmem.config import get_settings
from rootmem.storage.audit_protocols import AuditLogRepository
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from tests.unit.storage.audit_contract import AuditLogRepositoryContract


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    created_pool = await create_pool(get_settings())
    try:
        yield created_pool
    finally:
        await created_pool.close()


class TestPostgresAuditLogRepository(AuditLogRepositoryContract):
    @pytest.fixture
    def repository(self, pool: asyncpg.Pool) -> PostgresAuditLogRepository:
        self._pool = pool
        return PostgresAuditLogRepository(pool)

    async def tamper(
        self, repository: AuditLogRepository, namespace: str, seq: int, payload: dict[str, Any]
    ) -> None:
        # The append-only trigger blocks UPDATE, so simulate a privileged
        # attacker by disabling it for this one statement (test-only).
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
            await conn.execute(
                "UPDATE audit_log SET payload = $3::jsonb WHERE namespace = $1 AND seq = $2",
                namespace,
                seq,
                json.dumps(payload),
            )
            await conn.execute("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_append_only")

    async def test_trigger_rejects_update_and_delete(
        self, repository: PostgresAuditLogRepository, pool: asyncpg.Pool
    ) -> None:
        ns = self._ns()
        await repository.append(ns, "t", "remember", "memory", "m1", {})
        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                await conn.execute("UPDATE audit_log SET actor = 'x' WHERE namespace = $1", ns)
            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                await conn.execute("DELETE FROM audit_log WHERE namespace = $1", ns)
