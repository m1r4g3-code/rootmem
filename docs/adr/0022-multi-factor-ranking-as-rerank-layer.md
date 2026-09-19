# ADR 0022: Multi-factor ranking is a pure re-rank layer over hybrid candidates

**Status:** Accepted
**Date:** 2026-09-19

## Context

`search_hybrid` computes text+vector inside SQL. Adding decay, salience, trust and graph proximity there would bury five signals in one query and make them untestable in isolation.

## Decision

SQL keeps producing relevance candidates, over-fetched by a factor. A pure `rank_score` in Python then combines the five terms and returns a score plus a per-term breakdown. Missing terms drop out and weights renormalize.

## Alternatives considered

- SQL-only formula: rejected, hard to test and evolve.
- Learned/bandit ranking: rejected, no usage data.

## Consequences

Formulas live in `docs/math-spec/phase4-math-spec.md`; defaults are provisional `Settings` values. Candidate over-fetch bounds the cost.
