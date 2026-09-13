# Phase 0 Requirements & Constraints — Foundations

## Exit criterion (from the Build Reference, verbatim)

> An agent remembers a fact across two separate sessions via MCP.

Concretely: a fact written via the `remember` tool in one MCP client session (Claude Code or Cursor) must be retrievable via `recall` or `search` in a *separate, later* session of the same client, after the client process has fully restarted. This is the single pass/fail gate for tagging `v0.0.1-phase0`.

## Functional requirements

- FR1: Expose exactly 5 MCP tools — `remember`, `recall`, `update`, `forget`, `search` — over stdio transport.
- FR2: `remember` persists a fact with at minimum: content, source, timestamp, confidence. Supports an optional client-supplied `idempotency_key` so retries don't create duplicates.
- FR3: `recall` retrieves a single record by `id` or by `key`, scoped to a `namespace`.
- FR4: `search` retrieves ranked results by free-text query (Postgres full-text search, no semantic/embedding search yet), scoped to a `namespace`.
- FR5: `update` modifies content/confidence/metadata of an existing, non-deleted record.
- FR6: `forget` soft-deletes a record (sets `deleted_at`/`deleted_reason`); never issues a hard `DELETE`. Idempotent — repeated calls on an already-deleted record succeed and return the existing deletion timestamp rather than erroring.
- FR7: Soft-deleted records are excluded from `recall`/`search` results by default but remain physically present and inspectable (e.g. via direct `psql`) for audit purposes.

## Non-functional requirements

- NFR1 (latency budget): each tool call should complete in well under 500ms against a local Docker Postgres under normal (non-adversarial, non-loaded) conditions — this is a sanity budget for a single-row read/write against an indexed table, not a tuned SLA; it exists to catch gross regressions (e.g. an accidental full-table scan), not to gate shipping on a specific number.
- NFR2 (consistency): single-row operations only in Phase 0 — no multi-record transactions, no distributed consistency concerns. Postgres's own ACID guarantees are sufficient.
- NFR3 (failure modes): see `docs/adr/` hardening notes and the plan's Hardening section — Postgres/Redis unavailability must fail the specific tool call cleanly (`StorageError`) without crashing the MCP server process or corrupting state; a failed migration must not leave the schema half-applied.
- NFR4 (type safety): `mypy --strict` passes with zero errors across `src/rootmem/`.
- NFR5 (testability): all core logic (tool handlers, validation) must be unit-testable via the `InMemoryMemoryRepository` fake with zero Docker dependency; only true storage-integration behavior requires Docker.
- NFR6 (schema forward-compatibility): every stored record carries `schema_version`; the embedding column exists but is dimension-unconstrained and unpopulated (see ADR 0001 in the Vector Dimension decision within the plan) so Phase 1 can fix a dimension and add an index via a normal migration, not a redesign.
- NFR7 (idempotency): `remember` (via `idempotency_key`) and `forget` are safe to call more than once with the same arguments without duplicating or corrupting state.
- NFR8 (observability): every tool invocation emits a structured log entry with operation name, latency, and success/failure — no bare `print`, no swallowed exceptions.
- NFR9 (config): all connection strings, ports, and credentials come from environment variables via `pydantic-settings`, validated at startup (fail fast, clear error message) — nothing hardcoded.

## Explicit non-goals for Phase 0

Restated from the plan's "Explicitly out of scope" section — these are non-goals, not deferred requirements to sneak in early: semantic/embedding search, LLM-based extraction, consolidation, decay/salience/trust scoring, graph store, audit-log/lineage tracking, REST API, framework adapters, dashboard, multi-tenant auth, procedural memory, cross-instance continuity.

## Traceability to charter global standards

| Charter standard | How Phase 0 satisfies it |
|---|---|
| Type safety everywhere | `mypy --strict` CI gate |
| Schema versioning from day one | `schema_version` column, default 1 |
| Every write is attributable | `source`, `source_session_id`, `confidence`, `created_at` columns populated on every `remember` |
| Every destructive operation is soft | `forget` sets `deleted_at`/`deleted_reason`; no `DELETE FROM` anywhere in the codebase |
| Idempotency by default | `idempotency_key` on `remember`; idempotent `forget` |
| Observability from first commit | `observability/metrics.py` structured logging + latency timing |
| No unbounded LLM calls | Vacuously satisfied — Phase 0 makes zero LLM calls |
| Config over code | `pydantic-settings`-based `config.py`, env-var driven |
| Everything testable in isolation | `MemoryRepository` Protocol + `InMemoryMemoryRepository` fake, contract-tested against both implementations |
