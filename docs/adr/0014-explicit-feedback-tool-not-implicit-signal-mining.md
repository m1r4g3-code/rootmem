# ADR 0014: An explicit `feedback` MCP tool supplies retrieval-outcome feedback, not implicit signal-mining

**Status:** Accepted
**Date:** 2026-09-18

## Context

ADR 0008 named "real retrieval-outcome feedback" as the specific thing Phase 1 lacked to calibrate a genuine Bayesian posterior against, and named Phase 2 as where that feedback loop would exist. Nothing about what "retrieval-outcome feedback" concretely means was specified — it needed a real design decision this phase, not just a formula (ADR 0013) with no way to receive the evidence that formula's fourth call site (explicit feedback) actually consumes.

## Decision

A new `feedback` MCP tool (`relation_id`, `namespace`, `outcome: "confirmed" | "contradicted"`, `confidence: float = 1.0`, `note: str | None = None`) is the sole mechanism by which retrieval-outcome feedback enters the system. Calling it records a `relation_feedback` row and applies `apply_evidence` (ADR 0013) to the target relation's belief, using `bayesian_source_reliability_feedback` (default `1.0`) as the reliability weight — an explicit agent judgment is trusted fully, unlike an LLM extraction's own stated confidence.

`search` and `related` calls are **not** treated as any form of corroborating signal. A read proves a fact was retrieved, not that it was validated as correct — an agent could read a stale or wrong fact and still be about to correct it, or read a fact purely out of curiosity with no bearing on its truth.

## Rationale

Fabricating a validation signal from access patterns would be actively worse than having no feedback loop at all: it would feed spurious "corroboration" into the Bayesian update for facts that were never actually checked, silently inflating confidence in whatever gets read most often rather than whatever is most often correct — the exact failure mode a principled Bayesian design is supposed to avoid. An explicit tool costs almost nothing to add (it reuses 100% of already-proven MCP tool/schema/Protocol infrastructure — the same `_validated`/`ToolError` pattern every other tool already uses) and produces a signal with actual epistemic content: an agent (or the human behind it) asserting, after the fact, whether a specific relation turned out to be right or wrong.

## Alternatives considered

- **Implicit signal-mining from `search`/`related` call logs** (e.g. treating repeated retrieval of the same relation as corroboration). Rejected: conflates "read" with "validated," a category error with no way to distinguish "this was checked and confirmed correct" from "this was read and happened to be wrong" from "this was read for an unrelated reason."
- **A generic "rate this memory" tool covering both `memories` and `relations`.** Considered — rejected for this phase specifically because `relations`' belief state (`belief_alpha`/`belief_beta`) is the only thing Phase 2's Bayesian math actually consumes; extending feedback to raw episodic `memories` rows has no defined effect yet (they have no belief state to update) and would be speculative scope not required by this phase's exit criterion.
- **Passive confidence decay when a relation goes unretrieved for a long time**, as an implicit negative signal. Rejected: this is squarely Phase 4's decay/forgetting-curve scope (`R(t)`), not retrieval-outcome feedback — conflating the two here would quietly pull Phase 4 work into Phase 2.

## Consequences

- `docs/requirements/phase2-requirements.md`'s exit criterion item (e) is directly and literally testable: call `feedback`, observe `belief_alpha`/`confidence` move.
- No inference layer over MCP call logs is built — `search`/`related` remain purely read paths with no side effects on graph state, preserving the existing property that reading never mutates.
- If a future phase finds implicit signals worth mining after all (e.g. an agent's own subsequent corrections observed through some other channel), that is a new, separately-justified decision — not something this ADR's silence on the matter should be read as quietly permitting.
