# ADR 0019: `session_outcome` is a new, explicit `ingest_session` signal, never inferred from `feedback`

**Status:** Accepted
**Date:** 2026-09-18

## Context

Procedural distillation (ADR 0017) needs to know whether a session represents a successful or failed attempt, to decide whether it's a skill candidate or a lesson candidate. Phase 2 already shipped `feedback`/`relation_feedback` (ADR 0014): an explicit, agent-reported signal about whether a *fact* (a `relations` row) was correct. It might seem like reusing that machinery — inferring "this session failed" from a `feedback(outcome="contradicted")` call touching a relation created during that session — avoids adding a new signal.

## Decision

`ingest_session` gains a new, explicit, optional parameter: `session_outcome: Literal["success", "failure"] | None = None`, threaded straight through to `NewMemory`/`MemoryRecord` and persisted per-episode. No inference layer is built. `remember` does not gain this parameter — it has no session/sequence concept for an "outcome" to attach to.

## Rationale

`relation_feedback` and `session_outcome` answer genuinely different questions about genuinely different aggregates: "was this specific fact correct?" (a claim about the world) versus "did this task attempt succeed?" (a claim about a sequence of actions). A session can extract a perfectly correct fact while still representing a failed task attempt overall (e.g. correctly noting "the config loader lacks a default" while the attempted fix for a *different* bug failed) — and conversely, a successful task attempt can happen to extract no relations feedback ever touches. Treating one as a proxy for the other would fabricate a correlation this project has no data to support, exactly the category error ADR 0014 already named and rejected once, when it chose an explicit `feedback` tool over mining `search`/`related` read logs as an implicit corroboration signal. Extending that same discipline here, rather than re-litigating it, keeps the project's stance on implicit-vs-explicit signals consistent across every phase that has faced this choice (Phase 2's `feedback` tool, now Phase 3's `session_outcome` flag).

`importance_flag` (Phase 2, FR1) is the direct precedent this decision mirrors: a cheap, optional, agent-supplied flag at write time, with zero inference machinery, used later by batch-time logic (salience scoring then, procedural distillation now).

## Alternatives considered

- **Infer session failure from `relation_feedback(outcome="contradicted")` events tied to relations created during that session.** Rejected per the reasoning above — a different aggregate, a different question, no real data yet correlating the two, and a repeat of a category error this project has already named and rejected once.
- **Infer session failure from `superseded_count`/`contested_count` in `ingest_session`'s own response** (a session whose extraction produced contested/superseded relations "must have gone wrong"). Rejected: contradiction and contestation are properties of the *belief update mechanism* (ADR 0013), triggered by ordinary fact corrections that have nothing to do with whether the underlying task succeeded — conflating them would produce a noisy, unvalidated signal.
- **A separate `report_session_outcome` MCP tool, called after the fact, rather than a parameter on `ingest_session` itself.** Rejected: `ingest_session` is already the one place a whole session's content arrives in one call; splitting outcome-reporting into a second round-trip adds MCP surface area and a coordination requirement (which `ingest_session` call does a later outcome report apply to?) for no benefit over a single optional parameter, mirroring exactly how `importance_flag` was added to the same call rather than as a separate tool.

## Consequences

- A session with no `session_outcome` supplied is simply never considered for procedural/lesson distillation — a normal, silent no-op, not an error or a missed opportunity flagged anywhere. Agents that don't know or care about this feature pay zero cost.
- `storage/models.py`'s `MemoryRecord`/`NewMemory` gain one more optional field, following the exact additive pattern `importance_flag`/`salience_score`/`consolidated_at` already established — no restructuring, no migration risk beyond one more nullable column.
- If real usage later shows a genuine correlation between `relation_feedback` outcomes and session success worth exploiting, that is a new, data-backed decision for a later phase to make deliberately — not something this ADR forecloses, just something it explicitly declines to guess at now.
