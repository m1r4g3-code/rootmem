"""Trust scoring (ADR 0024, docs/math-spec/phase4-math-spec.md). Pure."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrustParams:
    default_reliability: float = 0.5
    source_reliability: Mapping[str, float] = field(default_factory=dict)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def memory_trust(source: str, confidence: float, params: TrustParams) -> float:
    """Per-source reliability times the memory's own confidence, in [0, 1]."""
    reliability = params.source_reliability.get(source, params.default_reliability)
    return _clamp01(_clamp01(reliability) * _clamp01(confidence))


def skill_effectiveness(belief_alpha: float, belief_beta: float) -> float:
    """Posterior mean of a Beta(alpha, beta) belief over 'this skill works'."""
    if belief_alpha <= 0 or belief_beta <= 0:
        raise ValueError("belief_alpha and belief_beta must be > 0")
    return belief_alpha / (belief_alpha + belief_beta)
