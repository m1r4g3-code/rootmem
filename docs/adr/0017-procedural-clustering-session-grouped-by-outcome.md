# ADR 0017: Procedural clustering — session-grouped-by-outcome, then cross-session trace similarity

**Status:** Accepted
**Date:** 2026-09-18

## Context

Phase 2's retro carried forward an open question (`docs/research/phase2-research-memo.md:40`): does `consolidation/distill.py`'s existing clustering-then-LLM-abstraction pattern generalize cleanly to episodic→procedural distillation, or does procedural memory need a materially different clustering signal? Phase 2's `distillation_similarity_threshold` clusters *individual episodes* by raw content similarity — appropriate for a fact, which is one flat claim. A procedure is not one claim; it's an ordered sequence of steps whose combination constitutes the pattern. Clustering at the individual-episode level would merge disconnected steps of unrelated attempts purely because they share vocabulary (e.g. two different bugs whose first step is "the test fails").

`MemoryRecord`/`NewMemory` (`storage/models.py`) already carry `source_session_id`, populated by `ingest_session`'s `session_id` parameter — real, already-shipped structure, unexploited by any consolidation logic before this phase.

## Decision

Group episodes by `(namespace, source_session_id, session_outcome)` within one consolidation batch, filtering to groups with at least `procedural_min_session_length` episodes and a non-null `session_outcome`. Each qualifying group's episodes are ordered by `created_at` and newline-joined into one trace-summary text, embedded once via the already-injected `EmbeddingProvider`. Success-outcome trace embeddings are pairwise cosine-compared and clustered via `consolidation/clustering.py`'s existing `cluster_by_similarity(ids, pairs, threshold)` — **reused completely unmodified**, since it was already a generic function over `(id, id, similarity)` triples with no assumption about what the ids represent. `procedural_session_similarity_threshold` is set to **`0.80`**, carried over as a starting hypothesis from `distillation_similarity_threshold` and independently validated by `scripts/spike_session_trace_clustering.py` against real `voyage-4` embeddings of four session traces: two differently-worded successful traces of the same procedure, one failed session on a related-looking task, and one unrelated successful trace.

The spike's real numbers: the two matching successful traces scored `0.9364` cosine similarity; the *next-closest* pair (a successful trace to the unrelated failure) scored `0.4272` — a margin of roughly `0.51`, two orders of magnitude wider than Phase 2's own `0.005` near-miss margin for episode-level clustering. Every threshold tested from `0.70` through `0.90` reproduced the expected grouping exactly (two clusters of one, one cluster of two). Failure-outcome traces are never clustered with each other or with success traces; each qualifying failure session is treated as its own singleton candidate for lesson distillation (see ADR 0020's recurrence-gating decision).

## Rationale

**Why the wide margin, unlike Phase 2's threshold.** Session-trace summaries carry far more distinguishing content (three sentences of specific technical detail) than the single-sentence near-duplicates Phase 2's threshold was validated against, so two *unrelated* traces have much less incidental lexical/semantic overlap than two unrelated single facts might. This is a genuinely different signal, not a coincidence of one small spike — but it is exactly the "not re-derived from first principles, re-validated for a different embedding target" caution `docs/math-spec/phase3-math-spec.md` names, and the number should be watched, not assumed permanent, if it is ever pushed to noisier real session data.

**Why reuse `cluster_by_similarity` unmodified, rather than writing a new clustering function.** It genuinely validates Phase 2's own abstraction design: the function was already written generically (`memory_ids: list[str]` is really "any set of ids"; the pairs are already opaque similarity triples). Session ids substitute cleanly for memory ids with zero code change — the only new code is `consolidation/procedural_clustering.py`'s construction of the *input* (trace grouping, trace-summary embedding, the pairs themselves), which is exactly where the genuinely new logic belongs.

**Why a new, separate `ProceduralMemoryRepository` Protocol**, applying ADR 0006's "different aggregate → different Protocol" test: a distilled skill/lesson artifact is not a raw episode (`MemoryRepository`), not a graph fact (`GraphRepository`), and not a consolidation run record (`ConsolidationRepository`) — it has its own lifecycle (create, supersede-on-name-collision, hybrid search by content) that fits none of the three existing interfaces without mixing concerns the way ADR 0006/0016 already rejected for analogous cases.

## Alternatives considered

- **Cluster individual episodes by raw content similarity, same as Phase 2, and post-hoc group by session.** Rejected: this inverts the actual signal — two structurally identical procedures with even mildly different step-level phrasing could fail to cluster at the episode level, while unrelated sessions' individual steps could accidentally cluster on shared vocabulary. The trace-level signal is both more correct and, per the spike, more cleanly separated.
- **A new bespoke clustering function for session traces.** Rejected: `cluster_by_similarity` is already correctly generic; writing a second implementation of the same ~30-line union-find algorithm for a cosmetic reason (different id semantics) would be needless duplication ADR 0006's own precedent argues against.
- **Fold `ProceduralMemoryRepository` into `MemoryRepository` or `GraphRepository`.** Rejected for the same reason ADR 0016 rejected folding `ConsolidationRepository` into either: a skill/lesson is neither a raw episode nor a graph fact, and forcing it into either interface would mix unrelated aggregate concerns.

## Consequences

- `scripts/spike_session_trace_clustering.py` and its console output are the recorded evidence for `procedural_session_similarity_threshold=0.80` — not asserted from first principles, and its wide safety margin (vs. Phase 2's thin one) is itself a finding worth carrying into Phase 4's research memo if real usage ever narrows it.
- `tests/unit/consolidation/test_procedural_clustering.py` unit-tests `group_session_traces`/trace-pair construction against hand-built data (no real embeddings needed there); the spike itself is the real-embeddings regression check, re-run manually if the embedding model ever changes (Phase 1's own open item).
- A session whose steps straddle two separate consolidation batches is never grouped as one trace — each pass only clusters within its own currently-unconsolidated batch. Named explicitly as a known, carried-forward limitation in `docs/requirements/phase3-requirements.md`, not a bug.
