from __future__ import annotations

import math

import pytest

from rootmem.evaluation.metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank


def test_recall_counts_relevant_items_in_the_top_k() -> None:
    relevance = {"a": 3, "b": 1, "c": 0}
    assert recall_at_k(["a", "x", "b"], relevance, 3) == 1.0
    assert recall_at_k(["a", "x", "b"], relevance, 2) == 0.5
    assert recall_at_k(["x", "y"], relevance, 5) == 0.0


def test_recall_with_nothing_relevant_is_one() -> None:
    assert recall_at_k(["x"], {"c": 0}, 3) == 1.0


def test_reciprocal_rank_uses_the_first_relevant_position() -> None:
    relevance = {"a": 2}
    assert reciprocal_rank(["a"], relevance) == 1.0
    assert reciprocal_rank(["x", "y", "a"], relevance) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x", "y"], relevance) == 0.0


def test_ndcg_is_one_for_the_ideal_order_and_lower_otherwise() -> None:
    relevance = {"a": 3, "b": 1}
    assert ndcg_at_k(["a", "b"], relevance, 5) == pytest.approx(1.0)
    worse = ndcg_at_k(["b", "a"], relevance, 5)
    assert 0.0 < worse < 1.0
    assert ndcg_at_k(["x", "y"], relevance, 5) == 0.0


def test_ndcg_matches_a_hand_computation() -> None:
    # grades [1, 3] at positions 1, 2 versus ideal [3, 1]
    dcg = (2**1 - 1) / math.log2(2) + (2**3 - 1) / math.log2(3)
    ideal = (2**3 - 1) / math.log2(2) + (2**1 - 1) / math.log2(3)
    assert ndcg_at_k(["b", "a"], {"a": 3, "b": 1}, 2) == pytest.approx(dcg / ideal)


def test_ndcg_with_nothing_relevant_is_one() -> None:
    assert ndcg_at_k(["x"], {}, 3) == 1.0


def test_mean_of_empty_is_zero() -> None:
    assert mean([]) == 0.0
    assert mean([1.0, 3.0]) == 2.0
