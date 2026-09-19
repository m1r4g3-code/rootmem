# ADR 0035: Per-identity token-bucket rate limiting and an unauthenticated health endpoint

**Status:** Accepted
**Date:** 2026-09-19

## Context

Nothing stops one identity from saturating the server or the paid embedding/extraction APIs behind it. Operators also need a liveness check that does not need a token.

## Decision

A pure token bucket (`docs/math-spec/phase6-math-spec.md`) limits each identity, with rate and burst in `Settings`. Throttled calls fail before the tool body runs, so they have no side effects. `/healthz` runs `SELECT 1` and returns only `{"status": "ok"}` or 503, revealing nothing else.

## Alternatives considered

- Distributed limiting (Redis): rejected, ROOTMEM is single-node; the limit is per process and documented as such.
- A health check that reports versions or counts: rejected, information leak.

## Consequences

Restarting the server resets the buckets. Multi-node deployments would need a shared limiter, which is out of scope.
