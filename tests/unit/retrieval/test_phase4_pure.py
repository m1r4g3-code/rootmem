from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rootmem.audit.chain import GENESIS_HASH, AuditEntry, compute_hash, verify_chain
from rootmem.retrieval.decay import RetentionParams, retention, stability_days
from rootmem.retrieval.ranking import RankTerms, RankWeights, rank_score
from rootmem.trust.scoring import TrustParams, memory_trust, skill_effectiveness

NOW = datetime(2026, 9, 19, tzinfo=UTC)
PARAMS = RetentionParams(base_stability_days=7.0)


def test_retention_is_one_at_zero_elapsed() -> None:
    assert retention(NOW, None, NOW, 0, None, PARAMS) == pytest.approx(1.0)


def test_retention_decreases_with_time() -> None:
    recent = retention(NOW, None, NOW - timedelta(days=1), 0, None, PARAMS)
    old = retention(NOW, None, NOW - timedelta(days=30), 0, None, PARAMS)
    assert 0.0 < old < recent < 1.0


def test_access_count_and_salience_slow_decay() -> None:
    created = NOW - timedelta(days=14)
    base = retention(NOW, None, created, 0, None, PARAMS)
    accessed = retention(NOW, None, created, 10, None, PARAMS)
    salient = retention(NOW, None, created, 0, 1.0, PARAMS)
    assert accessed > base
    assert salient > base


def test_last_access_resets_the_clock() -> None:
    created = NOW - timedelta(days=60)
    stale = retention(NOW, None, created, 3, None, PARAMS)
    touched = retention(NOW, NOW - timedelta(days=1), created, 3, None, PARAMS)
    assert touched > stale


def test_backwards_clock_is_clamped() -> None:
    assert retention(NOW, NOW + timedelta(days=5), NOW, 0, None, PARAMS) == pytest.approx(1.0)


def test_stability_and_params_validation() -> None:
    assert stability_days(0, None, PARAMS) == pytest.approx(7.0)
    with pytest.raises(ValueError):
        RetentionParams(base_stability_days=0)


def test_memory_trust() -> None:
    params = TrustParams(default_reliability=0.5, source_reliability={"claude-code": 0.9})
    assert memory_trust("claude-code", 1.0, params) == pytest.approx(0.9)
    assert memory_trust("unknown", 1.0, params) == pytest.approx(0.5)
    assert memory_trust("claude-code", 0.5, params) == pytest.approx(0.45)


def test_skill_effectiveness() -> None:
    assert skill_effectiveness(1.0, 1.0) == pytest.approx(0.5)
    assert skill_effectiveness(4.0, 1.0) > skill_effectiveness(1.0, 4.0)
    with pytest.raises(ValueError):
        skill_effectiveness(0.0, 1.0)


def test_rank_breakdown_sums_to_score() -> None:
    ranked = rank_score(RankTerms(0.8, 0.5, 0.2, 0.9, 0.0), RankWeights())
    assert sum(ranked.breakdown.values()) == pytest.approx(ranked.score)
    assert set(ranked.breakdown) == {
        "relevance",
        "retention",
        "salience",
        "trust",
        "graph_proximity",
    }


def test_missing_terms_renormalize_not_penalize() -> None:
    only_relevance = rank_score(RankTerms(0.8), RankWeights())
    assert only_relevance.score == pytest.approx(0.8)
    assert set(only_relevance.breakdown) == {"relevance"}


def test_higher_retention_and_trust_rank_higher() -> None:
    weights = RankWeights()
    base = rank_score(RankTerms(0.7, 0.2, None, 0.3), weights)
    better = rank_score(RankTerms(0.7, 0.9, None, 0.9), weights)
    assert better.score > base.score


def _chain(n: int) -> list[AuditEntry]:
    entries: list[AuditEntry] = []
    prev = GENESIS_HASH
    for seq in range(1, n + 1):
        row_hash = compute_hash(
            prev, "ns", seq, "actor", "remember", "memory", f"m{seq}", {"k": seq}, NOW
        )
        entries.append(
            AuditEntry(
                namespace="ns",
                seq=seq,
                actor="actor",
                action="remember",
                target_type="memory",
                target_id=f"m{seq}",
                payload={"k": seq},
                created_at=NOW,
                prev_hash=prev,
                row_hash=row_hash,
            )
        )
        prev = row_hash
    return entries


def test_valid_chain_and_empty_chain() -> None:
    assert verify_chain(_chain(5)).valid is True
    assert verify_chain([]).valid is True


def test_payload_tamper_is_detected_at_that_row() -> None:
    entries = _chain(5)
    entries[2] = entries[2].model_copy(update={"payload": {"k": 999}})
    result = verify_chain(entries)
    assert result.valid is False
    assert result.first_broken_seq == 3


def test_deleted_row_is_detected() -> None:
    entries = _chain(5)
    del entries[1]
    result = verify_chain(entries)
    assert result.valid is False
    assert result.first_broken_seq == 3


def test_relinked_hash_still_breaks_downstream() -> None:
    entries = _chain(4)
    forged = compute_hash(
        entries[0].row_hash, "ns", 2, "actor", "remember", "memory", "m2", {"k": 42}, NOW
    )
    entries[1] = entries[1].model_copy(update={"payload": {"k": 42}, "row_hash": forged})
    result = verify_chain(entries)
    assert result.valid is False
    assert result.first_broken_seq == 3
