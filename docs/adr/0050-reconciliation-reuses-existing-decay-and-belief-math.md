# ADR 0050: Reconciliation reuses existing decay and belief math; no new model

**Status:** Accepted
**Date:** 2026-09-27

## Context

A contested relation's raw belief (`belief_alpha`/`belief_beta`) never changes without new evidence — comparing raw confidence again later would never resolve anything a first look didn't already decide. Something has to change with the passage of time alone. Phase 4 already built exactly that: `retrieval/decay.py`'s `retention()`, driven by elapsed time since a reference timestamp. Relations have `recorded_at` (transaction time) but no access-tracking; `retention()` already handles "never accessed" via `last_accessed_at=None, access_count=0`.

## Decision

Decayed confidence = `belief_confidence(alpha, beta) * retention(now, None, recorded_at, 0, None, params)`, using the *same* `decay_base_stability_days` setting memories already use — no second decay-stability constant for relations. The comparison rule reuses the existing `bayesian_supersede_margin` from `resolve_contradiction`, applied to decayed values instead of raw ones (full derivation: `docs/math-spec/phase8-math-spec.md`).

## Alternatives considered

- A dedicated relation-specific decay constant: rejected for now — no evidence yet that relations should decay at a different rate than memories; adding a second provisional constant with no data to justify it is exactly the kind of premature parameter proliferation this project has avoided elsewhere. Named as a real, cheap revisit if usage ever shows it matters.
- Adding access-tracking to relations (so a frequently-`related`-to relation resists decay like an accessed memory does): rejected as new schema/scope for a mechanism this phase deliberately kept small; named as the concrete way a future phase could let the *older*, well-established side of a contest actually hold its ground instead of inevitably fading.

## Consequences

Because relations have no access-tracking, decayed confidence is purely a function of elapsed time and the original belief — nothing a caller does (short of `feedback`, which touches raw belief directly and is unaffected by rumination) can currently make an old, contested relation resist eventual decay-driven resolution in favor of the newer side (see the math spec's derivation of why this is a foregone conclusion in the long run). Stated plainly as the phase's most important named limitation, not hidden.
