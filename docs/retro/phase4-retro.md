# Phase 4 Retrospective — Ranking, Decay, Trust & Tamper-Evident Audit Log

**Status:** Filled in after `v0.4.0-phase4`'s automated exit-criterion test (1 passed, 144.35s), 229 unit tests, 82 Postgres integration tests, ruff and `mypy --strict` clean, and a live manual pass (8/8) on 2026-09-19.

## What shipped

- Multi-factor ranking as a pure re-rank layer over hybrid candidates (ADR 0022): relevance, retention, salience, trust, graph proximity; missing terms drop out and weights renormalize; each result carries a per-term `breakdown` that sums to its score.
- Read-time exponential decay with stability grown by access count and salience (ADR 0023), backed by `last_accessed_at`/`access_count` on `memories`. Never destructive.
- Trust (ADR 0024): per-source reliability times confidence for memories; a Beta posterior fed by the explicit `report_skill_outcome` tool for skills and lessons, reusing `apply_evidence`.
- Graph proximity from `memory_entities` links and 1-hop neighbours, activated by an explicit `entity_name`/`entity_type`.
- A hash-chained, append-only, per-namespace audit log (ADR 0025) with a database trigger against UPDATE/DELETE, an `AuditLogRepository` Protocol (Postgres and in-memory, one shared contract suite), and the `verify_audit` tool.
- 13 MCP tools (added `report_skill_outcome`, `verify_audit`). Migrations 0007 and 0008.

## What worked

- **The contract-suite pattern held for the fifth phase.** One suite ran the audit log against the in-memory fake and real Postgres, including tamper detection and concurrent appends.
- **`as_of` made time testable through MCP.** Decay ordering was proven end to end without sleeping.
- **Spike before ADR.** The decay-curve comparison showed both curve families keep reinforced memories on top; it also exposed the exponential's flat tail, which is recorded in ADR 0023 as a named revisit trigger instead of a surprise later.
- **Live tamper check.** Altering one row directly in Postgres made `verify_audit` report exactly that row, and the report persisted across restarts.

## What didn't work / surprises

- **Reads bumped `updated_at`.** Found only in the live pass: the shared `set_updated_at` trigger fired on the access-tracking UPDATE, so a recall looked like a modification. The unit and contract suites could not catch it because no test asserted `updated_at` around a read. Fixed by migration 0008 (a transaction-local opt-out used by `record_access`) plus a contract test.
- **Tests and live data share one database.** The Postgres integration suites `TRUNCATE` shared tables. This wiped the Phase 3 manual skills, and later the Phase 4 live memories, and it made my first exit-test run fail when I ran it concurrently with those suites. Only the audit log survived, because it is not truncated. Lesson: never run integration suites alongside live checks or each other; a separate test database would remove the hazard.
- **The live MCP server ran stale code, twice.** Restarting the Claude Code session did not respawn the server process; an explicit `/mcp` reconnect did. Diagnosed by comparing the server process start time with the last file edit time. Worth documenting in every manual checklist's prerequisites.
- **`trust_score` column dropped from my own migration.** Trust is source reliability times confidence, both already stored, so caching it added a column with no reader. Removed before anyone depended on it.
- **The exit test seeds skills directly into Postgres.** Real skills come only from consolidating session traces, so the trust-for-skills proof uses seeded rows; the Phase 3 test covers real induction.

## Limits worth stating

- The audit chain is tamper-evident, not tamper-proof: a database superuser can rewrite the whole chain. If an audit append fails after a mutation has applied, the tool reports an error even though the change happened.
- Trust was not run live (needs `TRUST_SOURCE_RELIABILITY` in the server env); the automated test covers it.
- Ranking weights, S0 = 7 days and reliabilities are provisional; there is no usage corpus to tune on. Ranking quality is shown directional (orderings behave), not measured.

## Decisions to revisit in Phase 5

- Whether to add a separate test database (see above).
- Weight and stability calibration once real usage exists; a benchmark harness remains ADR 0026's revisit trigger.
- Whether very old, unreinforced memories need age-separation (exponential tail).
- Carried unchanged: session-trace batch scoping, 0.80 clustering thresholds, inline auto-trigger consuming the first episode of a fresh namespace.
- Cross-instance identity continuity and REST/remote transport, still unbuilt.

## Metrics captured

- Exit-criterion test wall time: 144.35s (one 35s pacing sleep for Voyage's 3 requests/minute cap).
- Unit tests: 229 passed in 3.4s. Postgres integration: 82 passed in 574s. `mypy --strict`: 140 files clean.
- Server handshake: 8.0s (warm cache), down from 12.3s cold in Phase 3; not a like-for-like comparison.
- Live: `find_skill` scores 0.349 (effectiveness 0.75) vs 0.233 (0.25); decay ordering 0.293 vs 0.264 at +30 days.
