"""Retrieval ranking.

Phase 0 left this module empty — its only ranking was `ts_rank()`, issued
inline in `PostgresMemoryRepository.search_text`. This is its first real
tenant: `hybrid_score`, a deliberately minimal linear blend of text rank and
cosine similarity (see docs/math-spec/phase1-math-spec.md for the full
justification of why this is provisional, not the Phase 4 multi-factor
formula `α·cosine_sim + β·R(t) + γ·salience + δ·trust + ε·graph_proximity`
this module is ultimately reserved for).
"""

from __future__ import annotations

from dataclasses import dataclass


def hybrid_score(
    text_rank: float,
    cosine_sim: float,
    weight_text: float,
    weight_vector: float,
) -> float:
    """A plain weighted linear blend — no normalization beyond what
    `ts_rank()`/cosine similarity already provide natively, no learned
    weighting. See docs/math-spec/phase1-math-spec.md for why more
    sophistication isn't attempted yet (no real usage data to fit against).
    """
    return weight_text * text_rank + weight_vector * cosine_sim


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Used by `InMemoryMemoryRepository`'s semantic/hybrid search (Postgres
    computes this natively via pgvector's `<=>` operator instead)."""
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")
    dot = float(sum(x * y for x, y in zip(a, b, strict=True)))
    norm_a = float(sum(x * x for x in a)) ** 0.5
    norm_b = float(sum(y * y for y in b)) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


@dataclass(frozen=True)
class RankWeights:
    """Provisional Phase 4 weights (docs/math-spec/phase4-math-spec.md)."""

    relevance: float = 0.50
    retention: float = 0.15
    salience: float = 0.10
    trust: float = 0.15
    graph_proximity: float = 0.10


@dataclass(frozen=True)
class RankTerms:
    """Each term is in [0, 1], or None when that signal is absent (it is
    then dropped and the remaining weights renormalize -- absence is never
    a penalty)."""

    relevance: float
    retention: float | None = None
    salience: float | None = None
    trust: float | None = None
    graph_proximity: float | None = None


@dataclass(frozen=True)
class RankedScore:
    score: float
    breakdown: dict[str, float]


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def rank_score(terms: RankTerms, weights: RankWeights) -> RankedScore:
    """Multi-factor score (ADR 0022). `breakdown` maps each present term
    name to its weighted, renormalized contribution and sums to `score`."""
    present: list[tuple[str, float, float]] = [("relevance", terms.relevance, weights.relevance)]
    for name, value, weight in (
        ("retention", terms.retention, weights.retention),
        ("salience", terms.salience, weights.salience),
        ("trust", terms.trust, weights.trust),
        ("graph_proximity", terms.graph_proximity, weights.graph_proximity),
    ):
        if value is not None:
            present.append((name, value, weight))
    total_weight = sum(weight for _, _, weight in present)
    if total_weight <= 0:
        return RankedScore(score=0.0, breakdown={name: 0.0 for name, _, _ in present})
    breakdown = {name: weight * _clip01(value) / total_weight for name, value, weight in present}
    return RankedScore(score=sum(breakdown.values()), breakdown=breakdown)
