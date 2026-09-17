"""Salience scoring (ADR 0016). Pure functions, zero I/O — the raw
per-memory similarity data these take as input is fetched once per
consolidation batch by `MemoryRepository.find_similar_pairs` (ADR 0015) and
handed in by `consolidation.distill`'s orchestration, not fetched here.

Full derivation: docs/math-spec/phase2-math-spec.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rootmem.config import Settings


@dataclass(frozen=True)
class SalienceWeights:
    novelty: float
    importance: float
    repetition: float
    task_relevance: float
    repetition_similarity_threshold: float
    repetition_saturation_count: int

    @classmethod
    def from_settings(cls, settings: Settings) -> SalienceWeights:
        return cls(
            novelty=settings.salience_weight_novelty,
            importance=settings.salience_weight_importance,
            repetition=settings.salience_weight_repetition,
            task_relevance=settings.salience_weight_task_relevance,
            repetition_similarity_threshold=settings.repetition_similarity_threshold,
            repetition_saturation_count=settings.salience_repetition_saturation_count,
        )


def compute_novelty(neighbor_similarities: list[float]) -> float:
    """1.0 (maximally novel) if no other episode was compared against;
    otherwise 1 minus the closest match's similarity -- a near-duplicate
    scores close to 0, a genuinely distinct episode scores close to 1."""
    if not neighbor_similarities:
        return 1.0
    return 1.0 - max(neighbor_similarities)


def compute_repetition(neighbor_similarities: list[float], weights: SalienceWeights) -> float:
    """How many of the compared episodes are near-duplicates (at or above
    `repetition_similarity_threshold`), capped at `repetition_saturation_count`
    so a fact repeated 20 times doesn't score proportionally higher than one
    repeated 3 -- a raw cap, not a fitted diminishing-returns curve."""
    count = sum(1 for s in neighbor_similarities if s >= weights.repetition_similarity_threshold)
    return min(1.0, count / weights.repetition_saturation_count)


def compute_salience(
    *,
    novelty: float,
    importance_flag: float,
    repetition: float,
    task_relevance: float,
    weights: SalienceWeights,
) -> float:
    return (
        weights.novelty * novelty
        + weights.importance * importance_flag
        + weights.repetition * repetition
        + weights.task_relevance * task_relevance
    )
