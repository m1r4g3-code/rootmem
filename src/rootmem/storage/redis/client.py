"""Redis connectivity only — Phase 0 scope per the plan.

No working-memory/session-cache logic yet: Redis is stood up and smoke-tested
now (docker-compose already includes it, and a stateless cache costs nothing
to start dark), but nothing reads or writes through it until a later phase
has session state worth caching.
"""

from __future__ import annotations

from redis.asyncio import Redis

from rootmem.config import Settings


def create_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url)


async def ping(client: Redis) -> bool:
    return bool(await client.ping())
