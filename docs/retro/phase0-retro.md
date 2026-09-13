# Phase 0 Retrospective — Foundations

**Status:** Template — fill in after `v0.0.1-phase0` is tagged and dogfooded for at least a few real sessions in Claude Code / Cursor.

This retrospective's findings become an explicit input to Phase 1's research memo, per the charter's chained SDLC (§3: "each phase's Step 12 retrospective becomes input to the next phase's Step 1 research memo").

## What shipped

_(Fill in: final tool signatures as implemented, any deviations from the plan and why, actual `mcp` package version pinned, actual latency numbers observed.)_

## What worked

_(e.g. did the repository Protocol / contract-test pattern actually catch a behavioral mismatch between the in-memory fake and Postgres during development? Did stdio transport integrate cleanly with both Claude Code and Cursor, or were there client-specific quirks worth recording?)_

## What didn't work / surprises

_(e.g. did the manual validation checklist surface anything the automated tests missed? Did `mypy --strict` require any friction with `asyncpg`'s type stubs? Any issue with the unconstrained `VECTOR` column type in practice?)_

## Decisions to revisit in Phase 1

- Graph store choice (ADR 0001) — was deferring the right call, or did anything in Phase 0 development suggest KuzuDB/AGE should be decided differently than assumed?
- Embedding dimension (deferred, unconstrained `VECTOR` column) — confirm the actual model choice and dimension before writing Phase 1's first migration.
- Anything about the `MemoryRepository` Protocol's method signatures that Phase 1's extraction pipeline or semantic store needs but Phase 0 didn't anticipate.

## Metrics captured

_(Fill in: p50/p95 latency for remember/recall/search against local Docker Postgres, measured via the structured logging added in `observability/metrics.py`.)_
