# Phase 4 Research Memo — Ranking, Decay, Trust & Audit Log

**Date:** 2026-09-19. Inputs: phase 0-3 retros, math-specs, ADR 0004/0014/0016, `trust/README.md`.

## What every prior phase deferred to Phase 4

1. Multi-factor retrieval ranking `alpha*relevance + beta*R(t) + gamma*salience + delta*trust + epsilon*graph_proximity`.
2. Decay / forgetting curve R(t) (Phase 0 math-spec left exponential vs power-law undecided).
3. Trust / provenance scoring (only Bayesian source-reliability constants exist).
4. A tamper-evident audit log building on `deleted_at`/`deleted_reason` (ADR 0004).
5. Carried items: batch scoping of session traces, 0.80 / min_recurrence calibration, startup latency (12.3s handshake vs 30s client timeout), skill effectiveness tracking.

## Repo findings (verified by reading code)

- `retrieval/ranking.py` holds only `hybrid_score`; Postgres `search_hybrid` computes the blend in SQL and does not call it.
- No access tracking exists, so R(t) has no input yet.
- No per-source trust column; `salience_score` may be NULL (ADR 0016), so ranking must treat NULL as a normal state.
- `search` is graph-unaware; `graph_proximity` needs new code.
- No audit/actor table in migrations 0001-0006. Next migration: 0007.

## Prior art and how it shapes decisions

- **Forgetting curves.** Ebbinghaus exponential `exp(-t/S)` with stability S growing on each recall (spaced-repetition family). Power-law often fits aggregate data better, but exponential-with-growing-stability is simple and has one interpretable parameter. Confirmed by a small spike (ADR 0023).
- **Rank fusion.** Retrieval stacks commonly re-rank a relevance candidate set with auxiliary signals instead of one SQL expression. Re-ranking keeps SQL simple and the math unit-testable (ADR 0022).
- **Tamper-evident logs.** A hash chain gives tamper evidence with one SHA-256 per row. Merkle trees add inclusion proofs and external anchoring, neither needed for a single-node log (ADR 0025).
- **Trust.** Combine source reliability with corroboration; reuse the Beta-Bernoulli machinery for skills rather than a second scheme (ADR 0024).

## Open questions carried out of this phase

- Are default ranking weights good on real usage? No corpus yet; weights ship provisional.
- Does a real benchmark harness pay for itself (ADR 0021 revisit trigger, unchanged)?
- Cross-instance identity continuity remains frontier work, not Phase 4.
