# Phase 8 Retrospective — Background Rumination

**Status:** Filled in after `v0.8.0-phase8`'s automated exit-criterion test (passed, real Postgres, a real bounded wait with no tool call in between), the full unit suite (370 passed), the full free integration suite (110 passed, 18m08s), and a live manual pass against a real standalone server (6/6) on 2026-09-27.

## What shipped

- **The first autonomous mechanism in this codebase (ADR 0049).** One `asyncio` loop, HTTP mode only, off by default (ADR 0051), that wakes on its own wall-clock schedule and reconciles contested relations with no request behind it.
- **Reconciliation reuses existing math entirely (ADR 0050):** Phase 2's Bayesian belief confidence and Phase 4's decay/retention curve, composed over a pair of relations — no new decay model, no new belief model.
- **Cross-namespace autonomous discovery, namespace-scoped explicit access (ADR 0052):** the loop scans every namespace's contested relations directly (trusted server-side infrastructure); the explicit `ruminate` tool stays authorized and namespace-scoped like every other tool.
- **A genuinely new kind of exit criterion (ADR 0053):** every prior phase proved itself by calling something and checking the response. This one seeds a scenario, starts a real server, waits a bounded real duration with *no* tool call, and only then observes — because the claim itself ("this happens unprompted") cannot be proven the old way.
- 2 new `GraphRepository` methods (`list_contested`, `resolve_contest`), contract-tested against fake and real Postgres; 10 new unit tests; 1 real-Postgres, real-wait exit-criterion test; the 14th MCP tool (`ruminate`).

## What worked

- **Reuse held up completely.** Nothing about decay, belief, or audit needed to be reinvented — the entire new mechanism is composition of Phase 2/4/5's own pure functions and patterns (the `_background_tasks`/lazy-provider style already established for one-shot background work, extended to a long-lived task).
- **The wait-and-observe exit criterion caught a real bug the same way Phase 7's did.** The first run of the exit-criterion test failed because rumination never started at all — the settings were configured under the wrong env var name (`ROOTMEM_RUMINATION_ENABLED` instead of the actual, correctly-unprefixed `RUMINATION_ENABLED`, matching this codebase's own existing convention for feature-specific settings like `RATE_LIMIT_PER_MINUTE`). Caught by checking the server's own log for a "loop started" line that should have been there and wasn't — not by assuming the env var name was right because it "read naturally."
- **The live manual pass produced a small, pleasant surprise:** watching the age-gate get enforced tick-by-tick over the loop's real lifetime (a contest observed still-contested, then found resolved on a *later* check once real time had passed further) was a more convincing, more legible demonstration of the mechanism's correctness than the automated test's single wait-then-check window — worth remembering as a technique for any future autonomous-process verification.

## What didn't work / surprises

- **The env var prefix mistake** (above) — a second instance, after Phase 7's `prompt`/`prompt_text` bug, of documentation/tests being written against an assumed name before it was ever exercised against the real running system. The lesson from Phase 7 (verify a contract by observing a real instance, not by describing it carefully) generalizes past external client contracts to this project's *own* configuration surface — an assumption about our own code's naming convention was just as capable of being silently wrong as an assumption about Claude Code's.
- **Seeding two independent contested pairs in the same namespace requires distinct subject entities.** An early draft of the exit-criterion test reused "Alice" for both the primary and the "too-young" selectivity pair; the second `create_relation` call corroborated or re-contested whatever the first pair's own resolution had already left active, instead of forming an independent contest. Fixed by using a second, unrelated subject ("Bob") — obvious in hindsight, not obvious while writing the scenario.
- **A `resolve_contest` contract test using a syntactically invalid id** ("missing" instead of a well-formed-but-nonexistent UUID) hit Postgres's own type-cast error before the application's `NotFoundError` logic ever ran — inconsistent with the established convention elsewhere in the same contract suite (`record_feedback`'s own not-found test already used an all-zeros UUID). Fixed to match; a reminder that a contract test's own inputs should follow the same conventions as its neighbors, not be improvised per-test.

## Limits worth stating

- **Rumination will, absent any reinforcement, eventually resolve every stale contest in favor of whichever side is newer** — a stated, deliberate simplification (decay only discounts, never restores, and relations carry no access-tracking to let the older side "earn" resistance the way an accessed memory can). Not a claim that newer is correct, just the honest, provisional default.
- **Three-or-more-way contests are handled defensively, not generally** — a group with more than two active contested relations sharing a key is skipped entirely (`pairs_skipped_ambiguous`) until it naturally returns to a pair.
- **No shared/distributed coordination** — same single-node limitation every other phase has already named for rate limiting; irrelevant until this project ever needs to scale out.
- **Only proven against relations created via direct repository/SQL seeding, not through real LLM extraction** — a deliberate scoping choice (this phase tests the autonomous mechanism, not extraction, which Phase 1/2 already prove separately), but real extraction-produced contests were never exercised end-to-end together with rumination.

## Decisions to revisit in Phase 9+

- Cross-batch retrospective clustering of episodic memories (named and deferred in the research memo) — the other rumination-shaped idea seriously considered and cut from this phase specifically to keep it scoped.
- Whether relations should ever get their own access-tracking, so a frequently-`related`-to relation can resist decay-driven resolution the way an accessed memory does.
- The real-benchmark-evidence effort and the graph-viewer idea, both still open from the pre-Phase-7 conversation and untouched by this phase.
- Carried unchanged: the q06 ranking regression, no shared rate limiter.

## Metrics captured

- Unit tests: 370 passed (includes 10 new rumination-specific tests). Free integration suite: 110 passed (18m08s, includes this phase's own exit-criterion test). Phase 8 exit-criterion test: 1 passed, real Postgres, ~73s runtime (dominated by the required real waits).
- `mypy --strict`: clean across the full repo (212 source files at last check).
- Live: 3 contested pairs seeded directly against real Postgres, all three resolved correctly (two autonomously, one on demand), audit chain valid throughout, clean process shutdown confirmed.
