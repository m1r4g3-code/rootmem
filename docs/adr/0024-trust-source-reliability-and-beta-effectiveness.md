# ADR 0024: Trust combines source reliability with Beta-posterior effectiveness for skills

**Status:** Accepted
**Date:** 2026-09-19

## Context

Trust exists only as Bayesian reliability constants; skills have no effectiveness signal.

## Decision

Memory trust is per-source reliability times confidence. Skills and lessons gain `applied_count`/`success_count` through an explicit `report_skill_outcome` tool feeding a Beta posterior via the existing `apply_evidence`.

## Alternatives considered

- Inferring skill success implicitly: rejected, same reasoning as ADR 0014 and 0019.
- A second scoring scheme: rejected, one Bayesian mechanism is enough.

## Consequences

Answers the Phase 3 open question: skill effectiveness belongs to trust, using the same posterior machinery as relations.
