# ADR 0049: Rumination is one `asyncio` loop in the existing server process, scoped to contested-relation reconciliation

**Status:** Accepted
**Date:** 2026-09-27

## Context

The user asked for the deeper half of "closer to consciousness": something that revisits memory on its own schedule, not on request. Every background-ish thing this codebase already has (the consolidation auto-trigger, lazy provider construction) still only starts in reaction to a call. A genuinely new class of process is needed — the first one — and the same infra-minimalism discipline every phase has held (ADR 0012 rejected Celery/RQ/n8n for consolidation; ADR 0006/0010 rejected new services elsewhere) applies here at least as strongly, since this is more novel, less proven territory.

## Decision

One `asyncio.create_task` loop, started in `main_async()` only when `ROOTMEM_TRANSPORT=http` and `RUMINATION_ENABLED=true`, running one rumination pass every `RUMINATION_INTERVAL_MINUTES` for the life of the process, cancelled cleanly on shutdown. Its scope, this phase, is exactly one mechanism: decay-adjusted reconciliation of contested relations (`extraction/contradiction.py`'s `"contest"` outcome) — not the broader "cross-batch clustering" idea also considered (research memo), kept out to avoid entangling two hard, independently-scopable problems.

## Alternatives considered

- A new worker/scheduler service (Celery beat, a cron container, n8n): rejected for the same reasons ADR 0012 already gave, more strongly here — nothing about a single-process background task justifies new infrastructure.
- Running rumination in stdio mode too: rejected — stdio sessions are per-client and typically short-lived; "wakes on its own schedule" has little meaning for a process that may not outlive a few minutes.

## Consequences

Rumination only exists for HTTP-mode deployments. The server process now has a task that outlives every individual request; shutdown must explicitly cancel it (unlike the fire-and-forget one-shot background tasks Phase 2 introduced, which complete on their own).
