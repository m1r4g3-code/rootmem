# ADR 0034: Identities carry a read or readwrite scope

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR 0029 authorizes by namespace ownership only. A dashboard or reviewer agent should be able to look without being able to change or delete.

## Decision

`identities.scope` is `read` or `readwrite` (default `readwrite`). A pure `scopes.py` names the read tools: `recall`, `search`, `related`, `find_skill`, `get_skill`, `verify_audit`. The `guarded` wrapper denies every other tool for a `read` identity before the body runs, so a denied call has no side effects and no audit entry. Access tracking triggered by `recall`/`search` is not treated as a user write.

## Alternatives considered

- Per-tool scopes: deferred, two scopes cover the stated need.

## Consequences

New tools must be classified as read or write when added; an unclassified tool defaults to write (denied for read identities).
