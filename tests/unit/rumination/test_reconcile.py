from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootmem.retrieval.decay import RetentionParams
from rootmem.rumination.reconcile import decayed_confidence, decide_reconciliation
from rootmem.storage.graph_models import RelationRecord

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
PARAMS = RetentionParams(base_stability_days=7.0)
MARGIN = 0.05


def _relation(recorded_at: datetime, alpha: float, beta: float) -> RelationRecord:
    return RelationRecord(
        id=f"r-{recorded_at.isoformat()}-{alpha}-{beta}",
        namespace="ns",
        subject_entity_id="alice",
        predicate="works_at",
        object_entity_id="acme",
        confidence=alpha / (alpha + beta),
        belief_alpha=alpha,
        belief_beta=beta,
        valid_from=recorded_at,
        recorded_at=recorded_at,
        metadata={"contested": True},
    )


def test_decayed_confidence_shrinks_with_elapsed_time() -> None:
    fresh = _relation(NOW, alpha=1.5, beta=1.5)
    stale = _relation(NOW - timedelta(days=30), alpha=1.5, beta=1.5)

    assert decayed_confidence(fresh, NOW, PARAMS) == 0.5  # no elapsed time, no decay
    assert decayed_confidence(stale, NOW, PARAMS) < 0.01  # heavily decayed


def test_new_wins_once_the_old_side_has_decayed_past_the_margin() -> None:
    older = _relation(NOW - timedelta(days=30), alpha=1.1, beta=0.9)  # confidence 0.55
    newer = _relation(NOW, alpha=1.5, beta=1.5)  # confidence 0.5, no decay

    decision = decide_reconciliation(older, newer, NOW, PARAMS, MARGIN)

    assert decision.action == "resolve"
    assert decision.winner_id == newer.id
    assert decision.loser_id == older.id


def test_old_can_win_when_its_original_belief_is_much_stronger() -> None:
    older = _relation(NOW - timedelta(days=1), alpha=9.5, beta=0.5)  # confidence 0.95
    newer = _relation(NOW, alpha=1.0, beta=1.0)  # confidence 0.5

    decision = decide_reconciliation(older, newer, NOW, PARAMS, MARGIN)

    assert decision.action == "resolve"
    assert decision.winner_id == older.id
    assert decision.loser_id == newer.id


def test_still_contested_when_the_gap_is_within_the_margin() -> None:
    older = _relation(NOW, alpha=1.2, beta=0.8)  # confidence 0.6, no elapsed time
    newer = _relation(NOW, alpha=1.1, beta=0.9)  # confidence 0.55

    decision = decide_reconciliation(older, newer, NOW, PARAMS, MARGIN)

    assert decision.action == "still_contested"
    assert decision.winner_id is None
    assert decision.loser_id is None


def test_a_clock_that_runs_backwards_never_inflates_confidence() -> None:
    """Mirrors retention()'s own clamping guarantee (Phase 4) -- reconciling
    against a `now` earlier than `recorded_at` must not crash or invert."""
    older = _relation(NOW, alpha=1.5, beta=1.5)
    newer = _relation(NOW, alpha=1.5, beta=1.5)
    past = NOW - timedelta(days=1)

    decision = decide_reconciliation(older, newer, past, PARAMS, MARGIN)

    assert decision.action == "still_contested"
