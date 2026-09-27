# Phase 8 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase8_exit_criterion.py`:
this phase's automated proof is already unusually strong (a real HTTP server
subprocess, real Postgres, a real bounded wait with no tool call, then a
read-only observation) — it *is* a live proof of the autonomous mechanism,
just not run through a persistent, operator-style deployment. This checklist
is the lighter, environment-specific companion: does it behave the same way
when actually run as a standalone server, not just inside a test harness.

**Status: PASSED (6/6).** Live pass complete 2026-09-27, real dev Postgres,
real standalone HTTP server (not a test subprocess), `RUMINATION_INTERVAL_MINUTES=0.5`
(30s), `RUMINATION_MIN_CONTEST_AGE_HOURS=0.02` (~72s).

## Prerequisites (as actually run)

1. HTTP-mode server on `127.0.0.1:8765`, real dev Postgres, identity
   `manual-p8` (`readwrite`, 1-day expiry) owning namespace `manual-phase8`.
2. Contested pairs seeded directly via `PostgresGraphRepository` (bypassing
   LLM extraction, same deliberate scoping as the automated exit-criterion
   test — this checks the autonomous mechanism, not extraction, which is
   already separately proven).

## Checklist

- [x] **Autonomous resolution, real deployment**: seeded a contested pair
  for "Alice" (older relation backdated 30 days, newer 2 hours — past the
  72s grace period), waited 40s (one interval, no tool call), then called
  `related` for the first time. It was already resolved: the older relation
  showed `superseded_by` set and `is_contested: false`; the newer showed
  `is_active: true, is_contested: false`.
- [x] **Audit attribution**: `PostgresAuditLogRepository.list_entries` showed
  `system:rumination` as the actor for both resolutions, never an identity.
- [x] **Selectivity**: a fresh, unbackdated contest ("Bob", both relations
  recorded at real "now") was confirmed still fully contested immediately
  after the first observation — correctly held back by the age gate. It was
  later observed resolved too, once enough real time had passed between
  checks for it to age past the 72s threshold on a subsequent tick — the
  gate is genuinely enforced tick-by-tick over the loop's real lifetime, not
  a one-shot check.
- [x] **Explicit tool**: a third contest ("Carol", freshly seeded) was
  confirmed untouched by `ruminate(force=false)` (`pairs_skipped_too_young:
  1`), then resolved immediately by `ruminate(force=true)`
  (`pairs_resolved: 1`), confirmed via `related` — this instance resolved in
  favor of the *older* side (near-simultaneous timestamps meant raw belief
  strength decided it, not decay), demonstrating the "either direction can
  win" behavior live, not just in a unit test.
- [x] **Clean shutdown**: `taskkill` on the server process(es) stopped
  cleanly with no hang and no error, despite the background rumination task
  running.
- [x] **Cleanup**: identity revoked, server stopped, temporary seeding
  scripts removed.

Not separately re-verified live (already covered elsewhere): "off by
default" (a config default, and every other phase's tests/CI already run
with it unset); a failing pass not crashing the loop (unit-tested directly
in `tests/unit/rumination/test_run_fake_backend.py`).

## Result log

Full request/response detail and timestamps are in this session's own
transcript; the summary above is the complete, faithful account. No
findings beyond what's already noted — this pass surfaced no new bugs
(both real bugs this phase found — ADR 0047-class issues do not apply here;
the one real bug specific to Phase 8, the wrong env var prefix, was already
caught and fixed before this pass, during the exit-criterion test's own
first failed run).
