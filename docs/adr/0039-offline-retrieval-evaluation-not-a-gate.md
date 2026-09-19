# ADR 0039: Retrieval quality is evaluated offline on a small labeled set and is not a release gate

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR 0026 left ranking quality unmeasured and named a benchmark as its revisit trigger. The user asked for evidence but not a pass/fail number in the gate.

## Decision

A labeled set (about 30 memories and 15 queries, graded relevance, simulated access and age) with recorded embeddings runs offline and deterministically against the in-memory repositories. It compares text-only, Phase 1 hybrid and Phase 4 multi-factor ranking on recall@k, MRR and nDCG@k, and tries a small weight grid. Results and limits go in `docs/benchmarks/phase6-retrieval-eval.md`. Defaults change only if the evidence is clear, as a separate ADR-noted decision.

## Alternatives considered

- A public benchmark: rejected, needs infrastructure this project has not built (ADR 0021/0026).
- Gating on a metric: rejected, a small synthetic set cannot support a threshold.

## Consequences

Findings are directional. The set is synthetic and small; the report says so.
