"""Bayesian belief update replacing ADR 0008's deterministic contradiction
rule (ADR 0013). Pure functions, zero I/O — both `PostgresGraphRepository`
and `InMemoryGraphRepository` call these so the decision logic is written
once, not duplicated the way the deterministic rule was (a real gap found
while planning this phase — see docs/research/phase2-research-memo.md).

Full derivation: docs/math-spec/phase2-math-spec.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from rootmem.config import Settings
    from rootmem.storage.graph_models import NewRelation, RelationRecord


@dataclass(frozen=True)
class BayesianSettings:
    """A small, dependency-free view over the `Settings` fields this module
    needs — kept separate from `pydantic_settings.BaseSettings` so this pure
    module has zero import-time dependency on the settings-loading machinery
    (matching `EmbeddingProvider`/`ExtractionProvider`'s port pattern of
    never importing their real config source directly)."""

    prior_strength: float
    supersede_margin: float
    reliability_extracted: float
    reliability_distilled: float
    reliability_feedback: float

    def reliability_for(self, derivation: Literal["extracted", "distilled"]) -> float:
        return (
            self.reliability_extracted if derivation == "extracted" else self.reliability_distilled
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> BayesianSettings:
        return cls(
            prior_strength=settings.bayesian_prior_strength,
            supersede_margin=settings.bayesian_supersede_margin,
            reliability_extracted=settings.bayesian_source_reliability_extracted,
            reliability_distilled=settings.bayesian_source_reliability_distilled,
            reliability_feedback=settings.bayesian_source_reliability_feedback,
        )


def apply_evidence(
    alpha: float,
    beta: float,
    *,
    confidence: float,
    reliability: float,
    prior_strength: float,
    supporting: bool,
) -> tuple[float, float]:
    """Adjust a `Beta(alpha, beta)` belief by one evidence event.

    `confidence` is the evidence's own strength in [0, 1]; `reliability` is
    a per-source-type trust weight in [0, 1]; `prior_strength` scales how
    much pseudo-count weight one event contributes. `supporting=False`
    (refuting evidence, e.g. `feedback(outcome="contradicted")`) swaps which
    side of the belief the weight lands on.
    """
    weight = reliability * prior_strength
    if supporting:
        return alpha + weight * confidence, beta + weight * (1 - confidence)
    return alpha + weight * (1 - confidence), beta + weight * confidence


def belief_confidence(alpha: float, beta: float) -> float:
    return alpha / (alpha + beta)


@dataclass(frozen=True)
class ContradictionDecision:
    """What `GraphRepository.create_relation` should do, and the resulting
    belief state to apply — decided once here so both storage
    implementations act on identical logic (verified by the shared
    `tests/unit/storage/graph_contract.py` suite).

    - "create": no active relation existed for this (subject, predicate) —
      insert `new` with the given fresh belief.
    - "corroborate": `new`'s object exactly matches the active relation's —
      no new row; update the *existing* relation's belief in place.
      `derivation` is upgraded to `"distilled"` if the corroborating
      evidence itself came from distillation, and left unchanged otherwise
      — a one-way upgrade (never downgraded back to `"extracted"`), so a
      relation that has ever been corroborated by a cross-episode
      distillation pass stays marked as such.
    - "supersede": a genuine contradiction whose posterior clears the
      existing relation's by `supersede_margin` — insert `new` with its own
      belief, supersede the old row exactly as Phase 1's mechanics did.
    - "contest": a genuine contradiction that does not clear the margin —
      insert `new` with its own belief, mark both relations contested,
      neither is superseded (Phase 1's escape hatch, unchanged).
    """

    action: Literal["create", "corroborate", "supersede", "contest"]
    belief_alpha: float
    belief_beta: float
    derivation: Literal["extracted", "distilled"]


def resolve_contradiction(
    previous: RelationRecord | None,
    new: NewRelation,
    derivation: Literal["extracted", "distilled"],
    settings: BayesianSettings,
) -> ContradictionDecision:
    reliability = settings.reliability_for(derivation)

    if previous is None:
        alpha, beta = apply_evidence(
            1.0,
            1.0,
            confidence=new.confidence,
            reliability=reliability,
            prior_strength=settings.prior_strength,
            supporting=True,
        )
        return ContradictionDecision(
            action="create", belief_alpha=alpha, belief_beta=beta, derivation=derivation
        )

    same_object = (
        previous.object_entity_id == new.object_entity_id
        and previous.object_literal == new.object_literal
    )
    if same_object:
        alpha, beta = apply_evidence(
            previous.belief_alpha,
            previous.belief_beta,
            confidence=new.confidence,
            reliability=reliability,
            prior_strength=settings.prior_strength,
            supporting=True,
        )
        # One-way upgrade: once corroborated by a distillation pass, a
        # relation stays marked distilled even if later corroborated again
        # by an ordinary single-episode extraction.
        upgraded_derivation = "distilled" if derivation == "distilled" else previous.derivation
        return ContradictionDecision(
            action="corroborate",
            belief_alpha=alpha,
            belief_beta=beta,
            derivation=upgraded_derivation,
        )

    # Candidate contradiction: the new relation's own belief is computed
    # fresh (a Beta(1,1) prior plus this one event) -- it does not touch the
    # old relation's belief, since this evidence is about a different claim.
    new_alpha, new_beta = apply_evidence(
        1.0,
        1.0,
        confidence=new.confidence,
        reliability=reliability,
        prior_strength=settings.prior_strength,
        supporting=True,
    )
    new_confidence = belief_confidence(new_alpha, new_beta)
    old_confidence = belief_confidence(previous.belief_alpha, previous.belief_beta)

    # New evidence wins by default -- including a tie between two equally-
    # uncorroborated single-shot facts, matching Phase 1's most-recent-wins
    # baseline for the ordinary case. It only loses (contests) when the old
    # relation's belief is *meaningfully stronger* than the new evidence,
    # i.e. corroboration has actually earned it resistance. This is the
    # concrete mechanism behind the exit criterion's requirement (d): a
    # fresh, uncorroborated fact offers no such resistance; three
    # corroborating restatements do.
    if old_confidence > new_confidence + settings.supersede_margin:
        return ContradictionDecision(
            action="contest", belief_alpha=new_alpha, belief_beta=new_beta, derivation=derivation
        )
    return ContradictionDecision(
        action="supersede", belief_alpha=new_alpha, belief_beta=new_beta, derivation=derivation
    )


def apply_feedback(
    alpha: float,
    beta: float,
    *,
    outcome: Literal["confirmed", "contradicted"],
    reported_confidence: float,
    settings: BayesianSettings,
) -> tuple[float, float]:
    """The fourth `apply_evidence` call site: an explicit `feedback` MCP
    call (ADR 0014) is the literal retrieval-outcome feedback ADR 0008
    named as Phase 2's own trigger condition."""
    return apply_evidence(
        alpha,
        beta,
        confidence=reported_confidence,
        reliability=settings.reliability_feedback,
        prior_strength=settings.prior_strength,
        supporting=(outcome == "confirmed"),
    )
