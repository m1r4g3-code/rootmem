from __future__ import annotations

import pytest

from rootmem.identity.ratelimit import TokenBucketLimiter
from rootmem.identity.scopes import READ_TOOLS, scope_allows


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_readwrite_scope_allows_everything() -> None:
    for tool in ("remember", "forget", "search", "brand_new_tool"):
        assert scope_allows("readwrite", tool)


def test_read_scope_allows_only_the_read_tools() -> None:
    for tool in READ_TOOLS:
        assert scope_allows("read", tool)
    for tool in (
        "remember",
        "update",
        "forget",
        "ingest_session",
        "consolidate",
        "feedback",
        "report_skill_outcome",
        "some_future_tool",
    ):
        assert not scope_allows("read", tool)


def test_burst_is_allowed_then_throttled() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=3, clock=clock)
    assert [limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_tokens_refill_over_time_up_to_the_burst() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=2, clock=clock)  # 1 token/second
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")

    clock.now += 1.0
    assert limiter.allow("a")
    assert not limiter.allow("a")

    clock.now += 3600.0  # long idle refills only to the burst, not beyond
    assert [limiter.allow("a") for _ in range(3)] == [True, True, False]


def test_keys_are_independent() -> None:
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=_Clock())
    assert limiter.allow("x")
    assert not limiter.allow("x")
    assert limiter.allow("y")


def test_backwards_clock_does_not_grant_tokens() -> None:
    clock = _Clock()
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=clock)
    assert limiter.allow("a")
    clock.now -= 500.0
    assert not limiter.allow("a")


@pytest.mark.parametrize(("rate", "burst"), [(0, 1), (-1, 1), (10, 0)])
def test_invalid_parameters_are_rejected(rate: float, burst: int) -> None:
    with pytest.raises(ValueError):
        TokenBucketLimiter(rate_per_minute=rate, burst=burst)
