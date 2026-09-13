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
    # protocol=2 (RESP2): redis-py defaults to negotiating RESP3 via HELLO,
    # which pre-6.0 Redis servers (including the legacy Windows Redis 3.0.504
    # port used as a native-install stopgap on this machine) don't support.
    # RESP2 works against every Redis version and Phase 0 uses no RESP3-only
    # feature, so pinning it costs nothing against the docker-compose target
    # (Redis 7.4) either.
    return Redis.from_url(settings.redis_url, protocol=2)


async def ping(client: Redis) -> bool:
    return bool(await client.ping())
