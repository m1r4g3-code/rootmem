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
