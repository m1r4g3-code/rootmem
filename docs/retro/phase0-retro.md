# Phase 0 Retrospective — Foundations

**Status:** Backfilled 2026-09-17, during Phase 1 wrap-up — this was left as
an unfilled template when `v0.0.1-phase0` was tagged (2026-09-13), a real
process gap: the charter's chained SDLC expects each phase's retro to feed
the next phase's research memo, and Phase 1's research memo was written
without it. Filled in now from the actual commit history and
`scripts/manual_recall_check.md`'s result log rather than fabricated after
the fact from memory, so every claim below is traceable to a real commit or
recorded observation.

## What shipped

Final tool signatures matched the plan as written: `remember` (idempotency-
key dedup), `recall` (exactly one of `id`/`key`), `update` (partial,
in-place), `forget` (idempotent soft-delete), `search` (`ts_rank()` full-text
only — no semantic search yet, by design). `MemoryRepository` as a
`typing.Protocol` with `InMemoryMemoryRepository` and
`PostgresMemoryRepository`, verified against one shared contract-test suite.
Per-operation latency+outcome logging (`observability/metrics.py`'s
`log_operation` decorator) wrapping every tool handler, ahead of any real
metrics backend. Deferred, not built: graph store (ADR 0001), embedding
generation (`content_embedding` provisioned as an unconstrained `VECTOR`
column, left dark), any LLM calls at all.

Deviation from the original plan: local dev never ran on the planned
docker-compose Postgres+Redis stack. Docker Desktop's WSL2 backend was
permanently stuck on this machine (`CreateVm` timeout, `0x800705b4` —
BIOS/corporate-IT/hypervisor-related, not fixable from inside a session),
forcing a native-Windows Postgres 17 + Redis fallback (commit `126c9e3`).
CI and any future production deployment are unaffected — both already
target the official Docker images on Linux runners.

## What worked

- **The repository Protocol / contract-test pattern caught two real bugs
  the in-memory fake could not.** Running the same contract suite against
  real native Postgres surfaced: `confidence` was declared `REAL` (32-bit
  float), silently corrupting round-tripped values like `0.9` into
  `0.8999999761581421`; and a syntactically-invalid id string crashed
  asyncpg's parameter binding as a raw `StorageError` instead of behaving
  as a clean "not found," which the in-memory fake's plain dict lookup
  never would have exposed. Both fixed in `126c9e3`. This is the pattern's
  first real validation, not just a design that looked good on paper — and
  Phase 1 later leaned on the exact same pattern for the graph store,
  where it caught another real bug (see `docs/retro/phase1-retro.md`).
- **`mypy --strict` had zero friction with `asyncpg`'s type stubs** —
  no `# type: ignore` anywhere in `storage/postgres/` or `storage/redis/`.
  Worth recording since it's the kind of dependency-typing gap that
  commonly forces suppressions, and here it simply didn't.
- **stdio transport integrated cleanly with Claude Code** — all 4 real
  end-to-end tests (subprocess + real `mcp` client protocol) passed, and
  the live manual cross-session validation passed on the first fully-
  configured attempt (see below for the one setup snag that preceded it).
- **The unconstrained `VECTOR` column with no index worked exactly as
  designed** — Phase 0 never populated or queried it, so there was nothing
  to migrate away from cleanly; Phase 1's `0002_pgvector_dimension.sql`
  fixed the dimension and added the HNSW index with a single `ALTER
  COLUMN`, no data migration needed.

## What didn't work / surprises

- **A real client-configuration snag, not a code bug**: the first attempt
  at the manual cross-session validation failed with "MCP server rootmem
  not found" because the Claude Code session was rooted at `~\Documents`
  instead of `~\Documents\Continuum` — `.mcp.json` is project-scoped and
  wasn't found from the wrong working directory. Resolved by reopening the
  session in the correct folder. Small, but a real first-run friction point
  worth remembering when writing setup docs for this project.
- **The manual checklist's "repeat in Cursor" item was skipped**, not
  failed — judged genuinely optional once the Claude Code cross-session
  proof (two independent client processes sharing one persisted fact
  through the MCP server) already satisfied the charter's exact exit
  criterion wording. Recorded as a deliberate scope call in
  `scripts/manual_recall_check.md`, not an oversight.
- **No aggregate p50/p95 latency numbers were ever actually captured** as
  a metrics artifact, despite `log_operation` emitting per-call
  `latency_ms` on every tool invocation from the start. The instrumentation
  shipped; nothing downstream of it ever aggregated or reported on it. This
  is an honest gap in this retro, not a filled-in number — see below.
- **A benign Windows-specific test-teardown quirk**: the anyio/mcp SDK
  stack raises a "cancel scope" `RuntimeError` during e2e test teardown on
  Windows, strictly after the real assertions have already passed. Worked
  around in the test fixture (`126c9e3`) rather than treated as a real
  failure — worth knowing about if it resurfaces in Phase 1+'s e2e tests
  (it also needed re-confirming there, see `tests/integration/conftest.py`).

## Decisions to revisit in Phase 1

- **Graph store choice (ADR 0001)** — deferring was the right call for
  Phase 0's scope; nothing in Phase 0 development suggested KuzuDB/AGE
  should have been decided differently *at the time*. But the deferral
  itself aged quickly: by Phase 1 kickoff (less than a week later), KuzuDB
  had been archived after an acquisition and Apache AGE's Windows story
  hadn't materially improved — both named candidates from Phase 0's
  research were effectively dead ends by the time Phase 1 re-evaluated
  them (see `docs/adr/0006-graph-as-postgres-tables-not-dedicated-engine.md`).
  Lesson for future phases: a deferred infra decision in a fast-moving
  ecosystem (graph DBs, embedding models) should assume its own research
  will be stale by the time it's revisited, not just deferred and trusted.
- **Embedding dimension (deferred, unconstrained `VECTOR` column)** —
  confirmed fine as a deferral mechanism; Phase 1 picked `voyage-4` at
  1024 dimensions and the migration to a fixed, indexed column was
  trivial specifically because Phase 0 never wrote real vectors into it.
- **`MemoryRepository` Protocol's method signatures** — Phase 1 added
  `search_semantic`/`search_hybrid` and a populated `content_embedding`
  field additively, with no restructuring of existing methods — confirming
  ADR 0003's own stated expectation ("adding the Phase 1 embedding-backed
  semantic search... means adding new Protocol methods, not restructuring")
  actually held up in practice, not just on paper.

## Metrics captured

No formal p50/p95 latency benchmark was ever run or recorded — this line
item from the original plan template was not completed, and this retro
records that honestly rather than inventing numbers after the fact. What
does exist: 54/54 tests green at tag time (31 unit, 23 integration,
including 4 real MCP subprocess e2e tests), and every tool call already
emits a structured `operation=... outcome=... latency_ms=...` log line via
`log_operation` — the raw data for a future p50/p95 pass exists in the logs
of any real run, it was just never aggregated into a reported number. If
this matters going forward, it's a small, well-scoped follow-up (parse
existing structured logs or add a tiny benchmark script), not a gap that
needs new instrumentation.
