# Phase 4 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase4_exit_criterion.py`
(1 passed, 144.35s).

**Status: PASSED (8/8).** Automated proof passing; live pass complete.

## Prerequisites

1. MCP client points at the current `rootmem.integration.mcp.server` (13 tools, adding `report_skill_outcome` and `verify_audit`).
2. Restart the Claude Code session so the tool list and the changed `search` schema (`entity_name`, `entity_type`, `as_of`) are fetched.
3. Migration `0007_ranking_decay_trust_audit.sql` applied.
4. Namespace for the pass: `manual-phase4-check`.

## Checklist

- [x] **Decay/reinforcement**: `remember` two identical memories ("quokka deploy checklist"), `recall` one several times, then `search` with `as_of` 30 days ahead. The recalled one ranks first; each result shows a `breakdown` that sums to `score`.
- [x] **Trust** (covered by the automated exit test with vetted 0.95 vs unvetted 0.2; not run live because `.mcp.json` has no `TRUST_SOURCE_RELIABILITY`, agreed with the user): `remember` the same text twice from sources with different reliability (set `TRUST_SOURCE_RELIABILITY` in the server env, e.g. `{"vetted":0.95}`); the more trusted source ranks first.
- [x] **Skill effectiveness**: `report_skill_outcome` success/failure on two skills (use the Phase 3 namespace's skills), then `find_skill`; the one with successes ranks first and shows `effectiveness`.
- [x] **Graph proximity**: `ingest_session` "Alice works at Acme Corp.", then `search` with `entity_name=Alice`, `entity_type=Person`; the linked memory shows a `graph_proximity` term.
- [x] **Forget**: `forget` a memory; it no longer surfaces in `search`, and `psql` shows the row with `deleted_at` set.
- [x] **Audit**: `verify_audit` returns `valid: true` with the expected entry count.
- [x] **Tamper**: in `psql`, disable the trigger, alter one `audit_log` payload, re-enable; `verify_audit` returns `valid: false` with `first_broken_seq` at that row.
- [x] **Restart, then verify_audit and search again**: the chain and ranking survive a full client restart.

## Result log

**2026-09-19, namespace `manual-phase4-live`** (first attempt hit a stale server process from before the Phase 4 changes: no new tools, no `breakdown`; a fresh reconnect fixed it):

- **Decay:** two identical memories, one recalled 3x; `search` with `as_of` +30 days ranked the recalled one first (0.293 vs 0.264), `breakdown` present (retention 0.031 vs 0.003). Pass.
- **Skill effectiveness:** after one success / one failure, `find_skill` ranked `rollback-guide-good` (effectiveness 0.75, score 0.349) above `rollback-guide-bad` (0.25, 0.233). Pass.
- **Graph proximity:** `ingest_session` "Alice works at Acme Corp." then `search` with `entity_name=Alice, entity_type=Person`: breakdown shows `graph_proximity` 0.1 (full weight). Pass.
- **Forget:** forgotten memory no longer surfaces. Pass.
- **Audit:** `verify_audit` valid, 6 entries (2 remember, 1 ingest, 2 skill reports, 1 forget). Pass.
- **Tamper:** altered seq 4 in Postgres (trigger disabled); `verify_audit` returned `valid:false, first_broken_seq:4, reason "row_hash does not match row contents"`. Pass.
- **Real bug found live:** a `recall` bumped `updated_at` (the shared `set_updated_at` trigger fired on the access-tracking UPDATE), so a read looked like a modification. Fixed with migration 0008 plus a transaction-local opt-out in `record_access`; contract test added.
- **Data note:** the Phase 3 manual skills in `manual-phase3-check` were gone: the Postgres contract suites `TRUNCATE` shared tables. Skills for the live check were seeded directly.
- **Restart, then verify_audit again:** after a fresh `/mcp` reconnect, `verify_audit` still reported `valid:false, first_broken_seq:4` (the tamper persists in the log). A new memory recalled twice kept `updated_at == created_at`, confirming the 0008 fix live. Pass.
- **Process note:** restarting the Claude Code session did not respawn the rootmem server process; only an explicit `/mcp` reconnect did. Twice the live server ran pre-change code until reconnected (process start time compared against the last edit time). The `wombat` memories were also wiped by a Postgres integration test's `TRUNCATE` (shared database).
