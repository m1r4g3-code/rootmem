# ADR 0016: Salience computed at consolidation time; `ConsolidationRepository` as a new, separate Protocol

**Status:** Accepted
**Date:** 2026-09-18

## Context

Phase 1's math-spec left `retrieval/ranking.py`'s `γ·salience` term as an unfilled placeholder, naming Phase 2 as where it gets computed. The Build Reference's own salience formula (`S = w1·novelty + w2·user_flagged_importance + w3·repetition_count + w4·task_relevance`) has two terms — novelty and repetition — that are inherently corpus-relative: computing them requires comparing one episode against others, not evaluating it in isolation. Phase 1's NFR1 set a ~2s latency budget for `remember`, specifically to keep unbounded-cost work out of the write path. Separately, consolidation itself (ADR 0012) needs to track its own run history (when did a namespace last consolidate, how many episodes/clusters/facts did that pass produce) — state that belongs to neither `memories` nor `relations`.

## Decision

Salience is computed once per episode, in batch, during a consolidation pass — never synchronously inside `remember`/`ingest_session`. Those two tools gain one new, cheap, optional input (`importance_flag`, a plain float the caller supplies) and nothing else changes about their latency profile; `novelty`/`repetition` are computed later, against whatever other episodes exist in the same consolidation batch, using the same pairwise-similarity query (`MemoryRepository.find_similar_pairs`) that feeds distillation clustering — one pgvector self-join serves both purposes, not two separate passes.

Consolidation run history is modeled as a new, separate Protocol, `ConsolidationRepository` (`storage/consolidation_protocols.py`), rather than folded into `MemoryRepository` or `GraphRepository`:

```python
class ConsolidationRun(BaseModel):
    id: str
    namespace: str
    trigger_reason: Literal["count", "time", "manual"]
    started_at: datetime
    completed_at: datetime | None
    episodes_processed: int
    clusters_formed: int
    facts_distilled: int

class ConsolidationRepository(Protocol):
    async def start_run(self, namespace: str, trigger_reason: str) -> ConsolidationRun: ...
    async def complete_run(self, run_id: str, episodes_processed: int, clusters_formed: int, facts_distilled: int) -> ConsolidationRun: ...
    async def get_last_run(self, namespace: str) -> ConsolidationRun | None: ...
```

Two implementations (`PostgresConsolidationRepository`, `InMemoryConsolidationRepository`), contract-tested identically to `MemoryRepository`/`GraphRepository`'s existing pattern.

## Rationale

**Salience timing:** synchronous novelty/repetition computation inside `remember` would mean every write's latency scales with corpus size (a similarity comparison against however many other episodes exist), directly violating NFR1's intent — a budget written specifically to catch exactly this kind of accidental unbounded work sneaking into the write path. Batch computation at consolidation time is bounded by `consolidation_batch_size` instead, a size this project controls.

**`ConsolidationRepository` as its own Protocol:** ADR 0006 already established the test this project uses for "does this need its own Protocol" — a genuinely different aggregate, not just a different table. A consolidation run is not a memory and not a relation; it is a record of *when the system did work*, with its own lifecycle (`start_run` → `complete_run`) that neither existing Protocol's method set has any natural home for. Folding `start_run`/`complete_run`/`get_last_run` into `MemoryRepository` (the closest existing candidate, since consolidation reads and marks `memories` rows) would mix "operations on individual memory records" with "operations on the batch process that touches many of them" in one interface — exactly the aggregate-mismatch ADR 0006 already used to justify `GraphRepository`'s own separateness from `MemoryRepository`.

## Alternatives considered

- **Salience computed synchronously in `remember`, against a small fixed-size recent-memory sample instead of the full corpus.** Rejected: still adds unbounded-feeling latency variance to the write path for a score nothing reads synchronously afterward (salience is only consumed by consolidation and, eventually, Phase 4's ranking formula) — there is no benefit to paying that cost eagerly.
- **A `consolidation_runs` table with no Protocol wrapper, queried directly from `consolidation/distill.py`.** Rejected: every other piece of durable state in this project goes through a Protocol with a fake, specifically so business logic (`consolidation/distill.py`'s orchestration) stays unit-testable without Postgres — bypassing that pattern here for expedience would be inconsistent with NFR5.
- **Fold consolidation-run tracking into `GraphRepository`.** Rejected: a consolidation run touches `memories` (marking them consolidated) at least as much as it touches `relations` (creating distilled ones) — it doesn't belong more naturally to the graph than to episodic storage; it belongs to neither, which is the actual signal for a third Protocol.

## Consequences

- `consolidation/distill.py`'s `run_consolidation` orchestration function is fully unit-testable against three fakes (`InMemoryMemoryRepository`, `InMemoryGraphRepository`, `InMemoryConsolidationRepository`) plus `ScriptedDistillationProvider`, with zero Postgres/Docker/external-API dependency — matching Phase 0/1's testing discipline exactly.
- `salience_score` on a `memories` row is `NULL` until that episode has actually been through a consolidation pass — a normal, expected state, not an error condition; any future consumer (Phase 4's ranking formula) must treat `NULL` salience as "not yet scored," not as zero.
- `tests/unit/storage/consolidation_contract.py` is a new shared contract suite, following the exact structure of `tests/unit/storage/contract.py`/`graph_contract.py`.
