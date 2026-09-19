"""Ranking metrics (docs/math-spec/phase6-math-spec.md). Pure.

`ranked` is the list of returned ids best-first; `relevance` maps an id to a
graded relevance (0 = irrelevant, higher = better). An id absent from
`relevance` counts as 0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def recall_at_k(ranked: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    """Fraction of all relevant items found in the top k (1.0 if nothing is
    relevant: there was nothing to miss)."""
    relevant = {item for item, grade in relevance.items() if grade > 0}
    if not relevant:
        return 1.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def reciprocal_rank(ranked: Sequence[str], relevance: Mapping[str, int]) -> float:
    """1 / rank of the first relevant item; 0 if none is returned."""
    for position, item in enumerate(ranked, start=1):
        if relevance.get(item, 0) > 0:
            return 1.0 / position
    return 0.0


def _dcg(grades: Sequence[int]) -> float:
    return float(
        sum((2**grade - 1) / math.log2(position + 1) for position, grade in enumerate(grades, 1))
    )


def ndcg_at_k(ranked: Sequence[str], relevance: Mapping[str, int], k: int) -> float:
    """Normalized discounted cumulative gain at k (1.0 if nothing is relevant)."""
    ideal = _dcg(sorted((g for g in relevance.values() if g > 0), reverse=True)[:k])
    if ideal == 0.0:
        return 1.0
    return _dcg([relevance.get(item, 0) for item in ranked[:k]]) / ideal


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
