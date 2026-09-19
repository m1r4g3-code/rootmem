"""Read-time memory retention R(t) (ADR 0023, docs/math-spec/phase4-math-spec.md).

`R = exp(-dt / S)` where stability `S` grows with access count and salience.
Pure and never destructive: it only scores, it never rewrites or deletes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class RetentionParams:
    base_stability_days: float = 7.0

    def __post_init__(self) -> None:
        if self.base_stability_days <= 0:
            raise ValueError("base_stability_days must be > 0")


def stability_days(access_count: int, salience: float | None, params: RetentionParams) -> float:
    salience_term = 1.0 + max(0.0, salience if salience is not None else 0.0)
    access_term = 1.0 + math.log1p(max(0, access_count))
    return params.base_stability_days * access_term * salience_term


def retention(
    now: datetime,
    last_accessed_at: datetime | None,
    created_at: datetime,
    access_count: int,
    salience: float | None,
    params: RetentionParams,
) -> float:
    """Retention in (0, 1]. Elapsed time is measured from the last access, or
    from creation if the memory was never accessed; a clock that runs
    backwards is clamped to zero elapsed time."""
    reference = last_accessed_at if last_accessed_at is not None else created_at
    elapsed_days = max(0.0, (now - reference).total_seconds() / _SECONDS_PER_DAY)
    return math.exp(-elapsed_days / stability_days(access_count, salience, params))
