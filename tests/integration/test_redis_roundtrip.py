"""Redis connectivity smoke test — Phase 0 scope only (see
rootmem.storage.redis.client's docstring: no working-memory logic yet)."""

from __future__ import annotations

import pytest

from rootmem.config import get_settings
from rootmem.storage.redis import client as redis_client


@pytest.mark.asyncio
async def test_ping() -> None:
    settings = get_settings()
    client = redis_client.create_client(settings)
    try:
        assert await redis_client.ping(client) is True
    finally:
        await client.aclose()
