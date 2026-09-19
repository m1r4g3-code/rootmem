#!/usr/bin/env python
"""Create the integration-test database and apply all migrations (ADR 0031).

The test database is `<POSTGRES_DB>_test` (or POSTGRES_TEST_DB). It is created
on the same server using the normal connection settings, then migrated.
Safe to re-run.

Usage:
    python scripts/create_test_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from yoyo import get_backend, read_migrations

from rootmem.config import Settings

MIGRATIONS_DIR = (
    Path(__file__).parent.parent / "src" / "rootmem" / "storage" / "postgres" / "migrations"
)


async def _create_if_missing(admin_dsn: str, test_db: str) -> bool:
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", test_db)
        if exists:
            return False
        # Identifier comes from our own settings, never user input; quote it.
        await conn.execute(f'CREATE DATABASE "{test_db}"')
        return True
    finally:
        await conn.close()


def main() -> int:
    configured = Settings().postgres_db
    admin_db = configured.removesuffix("_test")
    test_db = os.environ.get("POSTGRES_TEST_DB", f"{admin_db}_test")
    if test_db == admin_db:
        print("refusing: test database name equals the main database name", file=sys.stderr)
        return 1

    os.environ["POSTGRES_DB"] = admin_db
    admin_dsn = Settings().postgres_dsn
    created = asyncio.run(_create_if_missing(admin_dsn, test_db))
    print(f"{'Created' if created else 'Found existing'} database {test_db!r}.")

    os.environ["POSTGRES_DB"] = test_db
    backend = get_backend(Settings().postgres_dsn)
    migrations = read_migrations(str(MIGRATIONS_DIR))
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        backend.apply_migrations(to_apply)
        print(f"Applied {len(to_apply)} migration(s) to {test_db!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
