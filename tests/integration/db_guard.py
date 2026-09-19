"""Refuse destructive statements unless connected to a test database (ADR 0031)."""

from __future__ import annotations

import asyncpg
from asyncpg.pool import PoolConnectionProxy


async def assert_test_database(conn: PoolConnectionProxy[asyncpg.Record]) -> None:
    name = await conn.fetchval("SELECT current_database()")
    if not str(name).endswith("_test"):
        raise RuntimeError(
            f"refusing destructive test statement on database {name!r}: "
            "integration tests must run against a database whose name ends in '_test'"
        )


async def truncate(conn: PoolConnectionProxy[asyncpg.Record], tables: str) -> None:
    """`TRUNCATE <tables>`, but only on a `_test` database."""
    await assert_test_database(conn)
    await conn.execute(f"TRUNCATE {tables}")
