from __future__ import annotations

from rootmem.consolidation.salience import (
    SalienceWeights,
    compute_novelty,
    compute_repetition,
    compute_salience,
)

_WEIGHTS = SalienceWeights(
    novelty=1 / 3,
    importance=1 / 3,
    repetition=1 / 3,
    task_relevance=0.0,
    repetition_similarity_threshold=0.85,
    repetition_saturation_count=3,
)


class TestComputeNovelty:
    def test_no_neighbors_is_maximally_novel(self) -> None:
        assert compute_novelty([]) == 1.0

    def test_close_neighbor_lowers_novelty(self) -> None:
        assert compute_novelty([0.95]) == 1.0 - 0.95

    def test_uses_the_closest_match_not_the_average(self) -> None:
        assert compute_novelty([0.1, 0.9]) == 1.0 - 0.9


class TestComputeRepetition:
    def test_no_neighbors_above_threshold_is_zero(self) -> None:
        assert compute_repetition([0.5, 0.6], _WEIGHTS) == 0.0

    def test_counts_neighbors_at_or_above_threshold(self) -> None:
        assert compute_repetition([0.9, 0.86, 0.5], _WEIGHTS) == 2 / 3

    def test_saturates_at_saturation_count(self) -> None:
        assert compute_repetition([0.9, 0.9, 0.9, 0.9, 0.9], _WEIGHTS) == 1.0


class TestComputeSalience:
    def test_equal_weights_average_the_three_terms(self) -> None:
        score = compute_salience(
            novelty=0.9, importance_flag=0.0, repetition=0.0, task_relevance=0.0, weights=_WEIGHTS
        )
        assert score == 0.9 / 3

    def test_flagged_important_novel_memory_scores_higher_than_routine_redundant_one(self) -> None:
        """The exit criterion's own claim (b): a flagged-important, novel,
        one-off memory must score measurably higher than a routine,
        unflagged, redundant restatement."""
        important_novel = compute_salience(
            novelty=1.0, importance_flag=1.0, repetition=0.0, task_relevance=0.0, weights=_WEIGHTS
        )
        routine_redundant = compute_salience(
            novelty=0.1, importance_flag=0.0, repetition=1.0, task_relevance=0.0, weights=_WEIGHTS
        )
        assert important_novel > routine_redundant

    def test_task_relevance_weighted_to_zero_has_no_effect(self) -> None:
        with_relevance = compute_salience(
            novelty=0.5, importance_flag=0.5, repetition=0.5, task_relevance=1.0, weights=_WEIGHTS
        )
        without_relevance = compute_salience(
            novelty=0.5, importance_flag=0.5, repetition=0.5, task_relevance=0.0, weights=_WEIGHTS
        )
        assert with_relevance == without_relevance
