# ADR 0012: Consolidation execution model — inline trigger + explicit tool, no new worker infrastructure

**Status:** Accepted
**Date:** 2026-09-18

## Context

The Build Reference recommends n8n for orchestration/scheduling and Celery+Redis for the actual consolidation workers — reasonable general advice for a system with a persistent server process. ROOTMEM has never had one: the MCP server (`src/rootmem/integration/mcp/server.py`) is a stdio subprocess a client (Claude Code/Cursor) launches and owns the lifecycle of, per session. There is no always-running process to schedule a periodic job against, and every prior infrastructure decision in this project has deliberately avoided adding a new service specifically because of this dev machine's Docker/WSL2 constraints — ADR 0006 rejected a dedicated graph engine in favor of two more Postgres tables, ADR 0010 rejected an HTTP webhook listener in favor of a CLI entrypoint, both on exactly this basis. Consolidation needs *some* trigger mechanism, since the whole point of a "sleep cycle" is that it runs without an agent explicitly asking for it every time.

## Decision

Two complementary entry points, both using infrastructure already present in this project:

1. **An explicit `consolidate` MCP tool + `consolidation/cli.py`** (mirroring `capture/cli.py`'s exact shape: `python -m rootmem.consolidation.cli --namespace <ns> [--force]`) — runs one synchronous consolidation pass on demand. Checks the trigger condition first (`docs/math-spec/phase2-math-spec.md`'s `should_consolidate`) and cleanly no-ops if unmet, unless `force=True` bypasses the check (`trigger_reason="manual"`).
2. **An inline check inside `ingest_session`**, after a successful write: if the trigger condition is met, fire a background consolidation pass via `asyncio.create_task`, held in a server-level `set[asyncio.Task]` with a completion callback that discards it — the same backgrounding technique `server.py`'s `_LazyEmbeddingProvider`/`_LazyExtractionProvider` already proved out for a different problem (deferring slow client construction so it doesn't block the MCP handshake). `ingest_session` itself never awaits this task — its own response time is unaffected (NFR1).

No new process, no new service, no new scheduler.

## Rationale

Both named use cases — "run consolidation periodically" and "run consolidation because enough new episodes just arrived" — are fully satisfiable within the existing single-process model: a CLI entrypoint is trivially schedulable by whatever the operator already uses for periodic tasks (cron, Task Scheduler, a CI cron job) without ROOTMEM needing to run or manage a scheduler itself, and the inline check means consolidation also happens naturally as a side effect of normal usage without requiring any external scheduling at all for a single-user/small-team deployment. This mirrors ADR 0010's "webhook capture" reinterpretation almost exactly: the *capability* the source material asks for is preserved, the *implementation* is reshaped to fit infrastructure this project already runs.

## Alternatives considered

- **Celery + Redis workers, per the Build Reference.** Rejected: this project has never run a persistent worker process; adopting one now, for a job whose actual computational cost (a bounded batch of episodes, a handful of LLM calls) doesn't need dedicated worker infrastructure to manage, would be a disproportionate new-infra cost matched against ADR 0006/0010's established discipline.
- **n8n for scheduling.** Rejected for the same reason — n8n is already named as a *tool available* to the user's broader environment (see this session's tool list), but wiring ROOTMEM's own consolidation trigger through it would make an external workflow tool a load-bearing dependency of the core memory system's own correctness, which the project's Protocol/contract-test-driven design otherwise avoids entirely (every dependency ROOTMEM relies on today is either a database it owns or an `EmbeddingProvider`/`ExtractionProvider`-shaped port with a fake).
- **Inline-only, no explicit tool/CLI.** Considered as the more minimal option — rejected because a namespace that stops receiving `ingest_session` traffic (but still has unconsolidated episodes from before) would never consolidate without some external trigger; the CLI/tool gives an operator or a scheduled job a way to force the issue.
- **Explicit tool/CLI only, no inline trigger.** Rejected because it would mean consolidation never happens automatically at all, contradicting the entire premise of a "sleep cycle" running in the background rather than requiring an agent to remember to call `consolidate` itself.

## Consequences

- The exit criterion (`docs/requirements/phase2-requirements.md`) is written to accept *either* path — an automated test can call `consolidate(force=True)` directly rather than depending on timing-sensitive inline-trigger behavior, while the manual dogfooding pass (`scripts/manual_phase2_check.md`) exercises the inline path for real.
- If a future phase's usage volume genuinely outgrows a single bounded batch per pass (`consolidation_batch_size`), revisiting this ADR in favor of real worker infrastructure is the named escape hatch — not a silent scope creep back into this phase.
- `NFR10` (background task safety) exists specifically because an unreferenced `asyncio.create_task` is eligible for garbage collection mid-flight — a documented asyncio pitfall this design must not reintroduce.
