"""asyncpg connection pool lifecycle.

This is the one module in the storage layer allowed to import asyncpg
directly (per ADR 0003) — everything above it talks to `MemoryRepository`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from pgvector.asyncpg import register_vector

from rootmem.config import Settings


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Decode/encode jsonb as plain Python dict/list via the stdlib json module,
    so `MemoryRecord.metadata` round-trips without manual (de)serialization at
    every call site. Also registers pgvector's asyncpg codec so `VECTOR`
    columns round-trip as plain `list[float]` (Phase 1 — content_embedding)."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await register_vector(conn)


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.postgres_dsn, min_size=1, max_size=10, init=_init_connection
    )


@asynccontextmanager
async def pool_lifespan(settings: Settings) -> AsyncIterator[asyncpg.Pool]:
    pool = await create_pool(settings)
    try:
        yield pool
    finally:
        await pool.close()
