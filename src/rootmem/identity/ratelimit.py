"""Per-key token-bucket rate limiter (ADR 0035,
docs/math-spec/phase6-math-spec.md). Pure apart from the injected clock.

Single-process by design: buckets live in memory, so the limit is per server
process and resets on restart.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(
        self,
        rate_per_minute: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be > 0")
        if burst < 1:
            raise ValueError("burst must be >= 1")
        self._rate_per_second = rate_per_minute / 60.0
        self._burst = float(burst)
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str) -> bool:
        """Consume one token for `key`; False when the bucket is empty."""
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=self._burst, updated_at=now)
            self._buckets[key] = bucket
        elapsed = max(0.0, now - bucket.updated_at)  # a backwards clock adds nothing
        bucket.tokens = min(self._burst, bucket.tokens + elapsed * self._rate_per_second)
        bucket.updated_at = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False
