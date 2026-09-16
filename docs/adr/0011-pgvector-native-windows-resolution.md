# ADR 0011: pgvector on the local dev machine — hosted Neon Postgres, not a native Windows build

**Status:** Accepted
**Date:** 2026-09-16

## Context

Phase 0 left `pgvector` optional (the migration gracefully skipped the extension/column when unavailable), which is how Phase 0 development survived on a native Windows Postgres install with no pgvector binary. Phase 1 makes `pgvector` a hard requirement — real embeddings must be stored and indexed — so that graceful-skip path is no longer viable for local dev.

A timeboxed spike (`scripts/spike_pgvector_windows_build.md`) investigated the officially-documented Windows build process (Visual Studio's `nmake`, requiring the "Desktop development with C++" workload). Finding: this machine has no Visual Studio or standalone C++ Build Tools installation at all (`cl.exe`, `nmake.exe`, `vswhere.exe` all absent) — building pgvector here would first require installing that workload, a multi-gigabyte download and a real install step, before the documented `nmake` process could even be attempted.

This is a meaningfully different situation than the WSL2/Docker `CreateVm` failure that blocked so much of Phase 0: that failure had no known, session-reachable resolution (BIOS/hypervisor/corporate-IT territory). The pgvector Windows build, by contrast, is a fully documented, officially supported process with a known, bounded cost — it simply hadn't been attempted, and attempting it means a real machine-level change (installing a large toolchain) that shouldn't happen without confirming the user wants that outcome.

## Decision

Use a dedicated, isolated Neon Postgres project (`rootmem-dev`) for local dev — a new database (`rootmem`) and role (`rootmem`) created inside the account's existing Neon organization, deliberately isolated from that account's other, unrelated pre-existing project. pgvector is pre-enabled on Neon (`CREATE EXTENSION vector` succeeds immediately, confirmed against the live instance). `.env` (gitignored, never committed) points at it; `config.py` gained a `postgres_sslmode` setting (default `"prefer"`) since Neon mandates SSL and the prior local-Postgres DSN construction had no SSL handling at all.

**CI and production are unaffected by this decision** — they already use the official `pgvector/pgvector` Docker image on GitHub Actions' Linux runners, which works with zero issues, same as Phase 0.

## Rationale

The user was offered both real options — install the Visual Studio toolchain and build natively, or use a hosted instance — and chose the hosted path, which was then set up directly via the Neon API using an API key the user provided from their existing account (not a new account created on their behalf, which isn't something this session could or should do autonomously). This costs zero local machine changes and works immediately, at the trade-off of local dev now depending on network connectivity and one external account — a trade-off the user made knowingly, not one imposed by default.

Isolating the new database+role inside a *new* logical unit, rather than reusing anything in the account's existing unrelated Neon project, follows the same "don't touch what you weren't asked to touch" principle this project has applied elsewhere (e.g. creating a dedicated GitHub repo for this project rather than reusing an existing one).

## Alternatives considered

- **Install VS C++ Build Tools and build pgvector natively**, per `scripts/spike_pgvector_windows_build.md`'s documented process. Not rejected outright — offered to the user as a real option — but not chosen, in favor of the hosted path's zero-install cost.
- **Continue without pgvector locally**, testing vector-search code paths only in CI/against a temporary Docker instance when available. Rejected: Phase 1's exit criterion requires an actual end-to-end manual dogfooding pass (`scripts/manual_phase1_check.md`) through a live Claude Code session, which needs a real, working local server — deferring pgvector entirely would block that validation step.

## Consequences

- Local dev integration tests now run against a remote database — measurably slower (all 23 Phase 0 integration tests re-run and passed against Neon, but took ~5 minutes versus ~15 seconds against local Postgres, due to real network round-trip latency to `us-east-1`). This is an accepted cost of the local-dev-only stopgap, not a production concern.
- `postgres_sslmode` is a new, generally-useful config addition (not Neon-specific) — it defaults to `"prefer"`, which negotiates SSL with any host that offers it while still working against a local Postgres with no SSL configured at all, so this change doesn't regress the native-Postgres or docker-compose paths.
- If Docker Desktop's WSL2 issue is ever resolved on this machine, or the VS Build Tools are installed later, local dev can move back to a fully local setup by changing only `.env` — no code depends on which Postgres backend is running.
