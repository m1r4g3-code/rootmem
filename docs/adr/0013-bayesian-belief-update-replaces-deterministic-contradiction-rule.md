# ADR 0013: Bayesian belief update (Beta-Bernoulli) replaces the deterministic contradiction rule

**Status:** Accepted
**Date:** 2026-09-18

## Context

ADR 0008 shipped a deterministic rule in Phase 1 — most-recent-`valid_from`-wins above a flat `contradiction_confidence_floor` — explicitly as a placeholder, naming its own exit condition: "once there's real retrieval-outcome feedback to calibrate a genuine confidence-weighted Bayesian posterior against." Phase 2 supplies that feedback loop (the new `feedback` MCP tool, ADR 0014). Two real gaps in the Phase 1 rule, confirmed by direct code read during this phase's planning, also motivate replacing it rather than merely extending it: `extraction/contradiction.py` was promised but never created (the rule is duplicated inline in both `GraphRepository` implementations), and `create_relation`'s query never compares `object_entity_id`/`object_literal` — an identical restatement of the same fact is indistinguishable from a genuine contradiction and incorrectly supersedes the original.

## Decision

Model each relation's confidence as a Beta distribution's posterior mean, parameterized by two new stored columns, `belief_alpha`/`belief_beta` (`DOUBLE PRECISION`, default `1.0` each — a uniform `Beta(1,1)` prior). `confidence = belief_alpha / (belief_alpha + belief_beta)`, recomputed in the same transaction every time evidence changes — never independently assigned.

A single pure function, `apply_evidence` (`extraction/contradiction.py`), handles every evidence source by adjusting `(alpha, beta)` by a reliability-and-confidence-weighted pseudo-count (full derivation in `docs/math-spec/phase2-math-spec.md`). Four call sites reuse it: initial relation creation, corroboration (an exact-match restatement raises the existing relation's belief instead of superseding it — the first Phase 1 gap named above, now closed), candidate contradiction (a new relation for the same `(subject, predicate)` but a different object supersedes by default — including a tie between two equally-uncorroborated facts, matching Phase 1's most-recent-wins baseline for the ordinary case — and only contests if the *old* relation's posterior is already meaningfully stronger than the new evidence, by `bayesian_supersede_margin`), and explicit feedback (ADR 0014).

## Rationale

Corroboration vs. contradiction is now a real, structural distinction (comparing `object_entity_id`/`object_literal`, not just `(subject, predicate)`), closing a genuine Phase 1 bug rather than just adding math on top of it. The comparison being *relative* (new posterior vs. the old relation's own, possibly-strengthened, posterior) rather than *absolute* (a single fixed floor every contradiction is measured against) is what actually delivers "confidence-weighted": a relation with three corroborating restatements has earned a higher bar for what it takes to overturn it than one with a single, uncorroborated extraction — exactly the intuition a flat floor structurally cannot express. Fresh research into 2026 production/research belief-revision systems (`docs/research/phase2-research-memo.md`) converges on the same shape (confidence as an updatable Bayesian belief, evidence weighted by source reliability) rather than this being an invented-from-scratch design.

## Alternatives considered

- **Confidence recomputed dynamically at read time from a raw evidence-event log**, a pattern found in fresh research. Rejected as the default storage strategy: `search`, `related`, and every contradiction check read `confidence` far more often than evidence changes it, and Beta-Bernoulli conjugacy already makes `(alpha, beta)` a mathematically sufficient, cheap-to-read cache of the exact same information a full event-log replay would produce — paying a per-read replay cost would buy nothing this stored pair doesn't already give. The raw events are still recorded (`relation_feedback`) for auditability, just not read on the hot path.
- **Keep the flat confidence-floor rule, just make the floor configurable per-namespace.** Rejected: this doesn't address either real Phase 1 gap (repeated facts still misfiled as contradictions; the floor is still absolute, not relative to the specific relation's own evidentiary strength) — it would be a parameter tweak dressed up as calibration, not the real math ADR 0008 deferred to this phase.
- **Full AGM-compliant belief revision over belief sets with entailment closure.** Rejected as more machinery than one relation's scalar confidence needs — the AGM postulates (Success, Consistency, Relevance/minimal-change) are used as a design sanity-check, not implemented in full generality, per `docs/math-spec/phase2-math-spec.md`'s own honest scoping.

## Consequences

- `extraction/contradiction.py` now exists as ADR 0008 originally promised, called by both `PostgresGraphRepository.create_relation`/`InMemoryGraphRepository.create_relation` — the Bayesian math is written once, not duplicated the way the deterministic rule was.
- `GraphRepository.create_relation`'s public signature is unchanged; its contract (documented in the Protocol's docstring) changes to describe the Bayesian decision instead of the flat floor. `ContradictionResolution` gains `corroborated: bool` alongside the existing `contested: bool`.
- The reliability weights (`bayesian_source_reliability_extracted`/`_distilled`/`_feedback`) and `bayesian_prior_strength`/`bayesian_supersede_margin` are documented, reasonable defaults, not calibrated against real data — the same honest position ADR 0008 itself took toward Phase 1. Recalibrating them once real `feedback` usage exists is an open item carried to Phase 3/4's research memo.
- Existing Phase 1 tests asserting the flat-floor behavior (`tests/unit/extraction/test_contradiction.py` — currently empty/nonexistent since the module itself never existed — and any contract-test cases in `tests/unit/storage/graph_contract.py` that assumed a fixed floor) are rewritten for the Bayesian behavior, not kept alongside it.
