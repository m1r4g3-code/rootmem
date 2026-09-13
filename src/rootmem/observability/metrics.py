"""Per-operation latency + outcome instrumentation.

Every MCP tool handler is wrapped with `log_operation`, which emits one
structured log line per call carrying the operation name, latency, and
success/failure — the observability floor the charter requires from the
first commit, ahead of any real metrics backend (Prometheus/OTel come
later, once there's more than a handful of operations worth aggregating).
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from rootmem.logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")


def log_operation(
    operation: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for async functions: logs latency_ms and success/failure.

    Re-raises any exception after logging it — this decorator observes,
    it never swallows or converts errors.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            logger = get_logger()
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.warning(
                    "operation=%s outcome=error latency_ms=%.2f error=%s",
                    operation,
                    latency_ms,
                    exc,
                )
                raise
            latency_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "operation=%s outcome=success latency_ms=%.2f",
                operation,
                latency_ms,
            )
            return result

        return wrapper

    return decorator
