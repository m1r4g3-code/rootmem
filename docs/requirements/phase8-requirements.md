# Phase 8 Requirements — Background Rumination

## Scope

One autonomous mechanism: a background process, running only in HTTP-mode deployments, that periodically re-examines contested relations across every namespace and resolves what decay-adjusted evidence now supports, with no request triggering each pass (see `docs/research/phase8-research-memo.md`). An explicit `ruminate` MCP tool exposes the same logic on demand, namespace-scoped, for manual use and testing.

## Functional requirements

- **FR1 — Autonomous loop.** In `ROOTMEM_TRANSPORT=http` mode, when `RUMINATION_ENABLED=true`, a background task starts at server startup and runs one rumination pass every `RUMINATION_INTERVAL_MINUTES` (default 60), for as long as the server process runs — never triggered by, or blocking, any tool call. Cancelled cleanly on server shutdown.
- **FR2 — Opt-in, off by default.** `RUMINATION_ENABLED` defaults to `false`. This phase introduces the first mechanism that mutates existing data with no request behind it; existing deployments must not have their graph silently rewritten by an upgrade.
- **FR3 — Reconciliation rule.** For each contested pair, compare decay-adjusted confidence (reusing `retrieval/decay.py`'s `retention` and the existing `bayesian_supersede_margin`) and either supersede the losing side (in either chronological direction) or leave both contested, per the research memo's rule. A contest younger than `RUMINATION_MIN_CONTEST_AGE_HOURS` (default 1) is skipped unless `force=True` (the explicit tool only).
- **FR4 — Cross-namespace discovery, namespace-scoped action recording.** The autonomous loop discovers contested pairs across every namespace directly (no caller-supplied namespace); each resolution is still recorded against its own namespace's audit chain, with a fixed system actor distinguishing it from an authenticated caller's actions.
- **FR5 — Explicit `ruminate` tool.** `ruminate(namespace, force=False) -> RuminateResult` (pairs examined, pairs resolved) runs one pass scoped to one namespace, through the same `guarded`/`authorize_namespace` wrapper as every other tool — unlike the autonomous loop, which needs no such wrapper because it takes no caller-supplied namespace at all.
- **FR6 — Never destructive.** Every resolution is a soft-supersede (`valid_to`/`superseded_by`/`supersedes` set), exactly like every other contradiction-handling path since ADR 0004/0008 — no row is ever deleted or overwritten in place beyond its `metadata.contested` flag and bi-temporal fields.
- **FR7 — Audit.** Every resolution appends one audit entry per namespace, distinguishable from a human/agent-triggered action by actor.

## Non-functional requirements

- **NFR1 (testability without real elapsed time).** The reconciliation decision and one rumination pass are pure/orchestration functions taking an explicit `now`, unit-tested without sleeping. The autonomous *loop* itself is tested by running a real subprocess server with a short configured interval and waiting a bounded, short real duration — the one part of this phase that cannot avoid some real wall-clock wait, matching the research memo's own naming of this as a new kind of exit criterion.
- **NFR2 (no new infrastructure).** No new worker/queue/scheduler service — one `asyncio` task inside the existing server process, the same pattern already used for the consolidation auto-trigger and the lazy provider construction.
- **NFR3 (bounded failure).** A pass that raises is logged and does not crash the loop or the server; the next scheduled pass still runs.
- **NFR4 (contract-tested storage).** The two new `GraphRepository` methods (`list_contested`, `resolve_contest`) are contract-tested against both the fake and Postgres implementations identically to every existing method.

## Explicit non-goals

- Cross-batch retrospective clustering of episodic memories (named and deferred to Phase 9+ in the research memo).
- Access-tracking / decay stability specific to relations (reuses memories' existing `decay_base_stability_days`).
- Resolving 3-or-more-way contests generally (handled pairwise, defensively; a leftover row stays contested for a later pass).
- Any UI/dashboard for contested-relation history.
- Running the loop in stdio mode (a per-session, typically short-lived process — the autonomous premise doesn't meaningfully apply).
- A per-relation `feedback`-equivalent tool for contests (the existing `feedback` tool already lets a caller explicitly resolve any relation's belief; rumination is specifically the *unattended* path).

## Exit criterion (wait-and-observe — a new kind of proof for this project)

Every prior phase proved its mechanism via a direct call and its response. This phase's core claim — "something happens with nobody asking" — cannot be proven that way. The exit criterion instead:

1. Seeds a contested pair via the real contradiction pathway (two facts about the same subject/predicate, close enough in confidence to contest, exactly like Phase 2's own exit-criterion scenario), then backdates the older relation's `recorded_at` far enough into the past (a direct, test-only repository/SQL step) that decay-adjusted comparison would now resolve it.
2. Starts a real HTTP-mode server subprocess with `RUMINATION_ENABLED=true` and a short `RUMINATION_INTERVAL_MINUTES` (a few seconds, not the real 60-minute default).
3. Waits, in the test, for a bounded duration longer than one interval — making **no tool call of any kind** during the wait.
4. Only then calls a read-only tool (`related`, or `get_relation_by_id` equivalent) and confirms the contest was already resolved, and calls `verify_audit` to confirm the resolution is attributed to the fixed rumination actor, not any caller.
5. A second, still-too-young contest (created after the wait began, or within the min-contest-age window) is confirmed to remain untouched by the same pass — proving this isn't a blind "resolve everything" sweep.
6. The explicit `ruminate(namespace, force=True)` tool is separately proven to resolve a contest on demand, without waiting for the loop.
7. A pass that encounters a namespace with no contests, or a transient repository error, does not crash the loop — proven by a subsequent pass still running successfully afterward.
