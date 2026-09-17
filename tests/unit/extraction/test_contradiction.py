"""Unit tests for the Bayesian belief update (ADR 0013) — pure functions,
zero I/O. Full derivation: docs/math-spec/phase2-math-spec.md."""

from __future__ import annotations

from datetime import UTC, datetime

from rootmem.extraction.contradiction import (
    BayesianSettings,
    apply_evidence,
    apply_feedback,
    belief_confidence,
    resolve_contradiction,
)
from rootmem.storage.graph_models import NewRelation, RelationRecord

_SETTINGS = BayesianSettings(
    prior_strength=2.0,
    supersede_margin=0.05,
    reliability_extracted=0.7,
    reliability_distilled=0.85,
    reliability_feedback=1.0,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _relation(
    *,
    object_entity_id: str | None = "acme",
    object_literal: str | None = None,
    belief_alpha: float = 1.0,
    belief_beta: float = 1.0,
) -> RelationRecord:
    return RelationRecord(
        id="rel-1",
        namespace="ns",
        subject_entity_id="alice",
        predicate="works_at",
        object_entity_id=object_entity_id,
        object_literal=object_literal,
        belief_alpha=belief_alpha,
        belief_beta=belief_beta,
        confidence=belief_confidence(belief_alpha, belief_beta),
        valid_from=_NOW,
        recorded_at=_NOW,
    )


def _new_relation(
    *,
    object_entity_id: str | None = "acme",
    object_literal: str | None = None,
    confidence: float = 0.9,
) -> NewRelation:
    return NewRelation(
        namespace="ns",
        subject_entity_id="alice",
        predicate="works_at",
        object_entity_id=object_entity_id,
        object_literal=object_literal,
        confidence=confidence,
    )


class TestApplyEvidence:
    def test_supporting_evidence_raises_alpha_more_than_beta_for_high_confidence(self) -> None:
        alpha, beta = apply_evidence(
            1.0, 1.0, confidence=0.9, reliability=0.7, prior_strength=2.0, supporting=True
        )
        assert alpha > 1.0
        assert beta > 1.0
        assert (alpha - 1.0) > (beta - 1.0)

    def test_refuting_evidence_raises_beta_more_than_alpha_for_high_confidence(self) -> None:
        alpha, beta = apply_evidence(
            1.0, 1.0, confidence=0.9, reliability=0.7, prior_strength=2.0, supporting=False
        )
        assert (beta - 1.0) > (alpha - 1.0)

    def test_zero_reliability_leaves_belief_unchanged(self) -> None:
        alpha, beta = apply_evidence(
            2.0, 3.0, confidence=1.0, reliability=0.0, prior_strength=2.0, supporting=True
        )
        assert (alpha, beta) == (2.0, 3.0)


class TestResolveContradictionNoPrevious:
    def test_no_active_relation_creates_fresh_belief(self) -> None:
        decision = resolve_contradiction(
            None, _new_relation(confidence=0.9), "extracted", _SETTINGS
        )
        assert decision.action == "create"
        assert belief_confidence(decision.belief_alpha, decision.belief_beta) > 0.5


class TestResolveContradictionCorroboration:
    def test_identical_object_corroborates_not_supersedes(self) -> None:
        previous = _relation(object_entity_id="acme")
        decision = resolve_contradiction(
            previous, _new_relation(object_entity_id="acme", confidence=0.9), "extracted", _SETTINGS
        )
        assert decision.action == "corroborate"

    def test_corroboration_raises_confidence_above_original(self) -> None:
        previous = _relation(object_entity_id="acme", belief_alpha=2.26, belief_beta=1.14)
        original_confidence = belief_confidence(previous.belief_alpha, previous.belief_beta)
        decision = resolve_contradiction(
            previous, _new_relation(object_entity_id="acme", confidence=0.9), "extracted", _SETTINGS
        )
        new_confidence = belief_confidence(decision.belief_alpha, decision.belief_beta)
        assert new_confidence > original_confidence

    def test_identical_literal_object_also_corroborates(self) -> None:
        previous = _relation(object_entity_id=None, object_literal="blue")
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id=None, object_literal="blue", confidence=0.9),
            "extracted",
            _SETTINGS,
        )
        assert decision.action == "corroborate"

    def test_repeated_corroboration_compounds(self) -> None:
        """Three restatements in a row should keep raising confidence, not
        plateau after the first -- the exit criterion's own scenario."""
        confidences = []
        alpha, beta = 1.0, 1.0
        for _ in range(3):
            previous = _relation(object_entity_id="acme", belief_alpha=alpha, belief_beta=beta)
            decision = resolve_contradiction(
                previous,
                _new_relation(object_entity_id="acme", confidence=0.9),
                "extracted",
                _SETTINGS,
            )
            alpha, beta = decision.belief_alpha, decision.belief_beta
            confidences.append(belief_confidence(alpha, beta))
        assert confidences[0] < confidences[1] < confidences[2]


class TestResolveContradictionCandidateContradiction:
    def test_different_object_entity_is_a_candidate_contradiction(self) -> None:
        previous = _relation(object_entity_id="acme")
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id="globex", confidence=0.9),
            "extracted",
            _SETTINGS,
        )
        assert decision.action in ("supersede", "contest")

    def test_equally_weak_single_shot_contradiction_supersedes_by_default(self) -> None:
        # Two single-shot, equally-confident, equally-reliable facts are a
        # genuine tie by evidence strength -- but new evidence wins ties by
        # design (matching Phase 1's most-recent-wins baseline for the
        # ordinary case), not "contest by default". `previous` already
        # carries one 0.9-confidence extraction's belief (Beta(1,1) +
        # apply_evidence(confidence=0.9, reliability=0.7, prior_strength=2.0)
        # = alpha=2.26, beta=1.14 -- see docs/math-spec/phase2-math-spec.md's
        # own worked example); the new contradiction at the same confidence
        # produces the same posterior for itself, and still supersedes.
        previous = _relation(object_entity_id="acme", belief_alpha=2.26, belief_beta=1.14)
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id="globex", confidence=0.9),
            "extracted",
            _SETTINGS,
        )
        assert decision.action == "supersede"

    def test_low_confidence_contradiction_against_a_fresh_unevidenced_relation_supersedes(
        self,
    ) -> None:
        # A relation still at the raw Beta(1,1) prior (no evidence applied
        # yet) has confidence 0.5 -- trivially easy to overturn, correctly.
        previous = _relation(object_entity_id="acme")
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id="globex", confidence=0.9),
            "extracted",
            _SETTINGS,
        )
        assert decision.action == "supersede"

    def test_meaningfully_weaker_contradiction_against_a_strengthened_relation_is_contested(
        self,
    ) -> None:
        # `previous` has been corroborated three times (belief compounded
        # well above a single extraction's ~0.665); a new, single,
        # lower-confidence contradiction no longer clears it.
        previous = _relation(object_entity_id="acme", belief_alpha=4.78, belief_beta=1.42)
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id="globex", confidence=0.6),
            "extracted",
            _SETTINGS,
        )
        assert decision.action == "contest"

    def test_strengthened_belief_resists_contradiction_that_would_have_won_under_flat_floor(
        self,
    ) -> None:
        """The exit criterion's core proof: after real corroboration, the
        old relation's posterior is high enough that a fresh, single-shot
        contradiction at a lower confidence no longer clears it -- even
        though under Phase 1's flat floor (any confidence > 0.5 wins), the
        same contradiction would have superseded outright."""
        alpha, beta = 1.0, 1.0
        for _ in range(3):
            previous = _relation(object_entity_id="acme", belief_alpha=alpha, belief_beta=beta)
            decision = resolve_contradiction(
                previous,
                _new_relation(object_entity_id="acme", confidence=0.9),
                "extracted",
                _SETTINGS,
            )
            alpha, beta = decision.belief_alpha, decision.belief_beta
        strengthened = _relation(object_entity_id="acme", belief_alpha=alpha, belief_beta=beta)

        # A modest-confidence contradiction that would clear Phase 1's flat
        # 0.5 floor easily.
        weak_contradiction = _new_relation(object_entity_id="globex", confidence=0.6)
        decision = resolve_contradiction(strengthened, weak_contradiction, "extracted", _SETTINGS)
        assert decision.action == "contest"

    def test_high_confidence_contradiction_still_supersedes_a_weak_prior(self) -> None:
        previous = _relation(object_entity_id="acme")  # weak, uncorroborated prior
        decision = resolve_contradiction(
            previous,
            _new_relation(object_entity_id="globex", confidence=0.999),
            "distilled",
            _SETTINGS,
        )
        assert decision.action == "supersede"


class TestApplyFeedback:
    def test_confirmed_outcome_raises_confidence(self) -> None:
        alpha, beta = 2.0, 1.0
        original = belief_confidence(alpha, beta)
        new_alpha, new_beta = apply_feedback(
            alpha, beta, outcome="confirmed", reported_confidence=1.0, settings=_SETTINGS
        )
        assert belief_confidence(new_alpha, new_beta) > original

    def test_contradicted_outcome_lowers_confidence(self) -> None:
        alpha, beta = 2.0, 1.0
        original = belief_confidence(alpha, beta)
        new_alpha, new_beta = apply_feedback(
            alpha, beta, outcome="contradicted", reported_confidence=1.0, settings=_SETTINGS
        )
        assert belief_confidence(new_alpha, new_beta) < original
