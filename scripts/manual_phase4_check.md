# Phase 4 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase4_exit_criterion.py`
(1 passed, 144.35s).

**Status: PENDING.** Automated proof passing; live pass not yet executed.

## Prerequisites

1. MCP client points at the current `rootmem.integration.mcp.server` (13 tools, adding `report_skill_outcome` and `verify_audit`).
2. Restart the Claude Code session so the tool list and the changed `search` schema (`entity_name`, `entity_type`, `as_of`) are fetched.
3. Migration `0007_ranking_decay_trust_audit.sql` applied.
4. Namespace for the pass: `manual-phase4-check`.

## Checklist

- [ ] **Decay/reinforcement**: `remember` two identical memories ("quokka deploy checklist"), `recall` one several times, then `search` with `as_of` 30 days ahead. The recalled one ranks first; each result shows a `breakdown` that sums to `score`.
- [ ] **Trust**: `remember` the same text twice from sources with different reliability (set `TRUST_SOURCE_RELIABILITY` in the server env, e.g. `{"vetted":0.95}`); the more trusted source ranks first.
- [ ] **Skill effectiveness**: `report_skill_outcome` success/failure on two skills (use the Phase 3 namespace's skills), then `find_skill`; the one with successes ranks first and shows `effectiveness`.
- [ ] **Graph proximity**: `ingest_session` "Alice works at Acme Corp.", then `search` with `entity_name=Alice`, `entity_type=Person`; the linked memory shows a `graph_proximity` term.
- [ ] **Forget**: `forget` a memory; it no longer surfaces in `search`, and `psql` shows the row with `deleted_at` set.
- [ ] **Audit**: `verify_audit` returns `valid: true` with the expected entry count.
- [ ] **Tamper**: in `psql`, disable the trigger, alter one `audit_log` payload, re-enable; `verify_audit` returns `valid: false` with `first_broken_seq` at that row.
- [ ] **Restart, then verify_audit and search again**: the chain and ranking survive a full client restart.

## Result log

_(pending)_
