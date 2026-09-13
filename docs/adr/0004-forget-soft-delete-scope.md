# ADR 0004: `forget` scope — soft-delete only, no audit log yet

**Status:** Accepted
**Date:** 2026-09-13

## Context

The charter mandates "every destructive operation is soft. No hard deletes in core stores — quarantine/archive with an audit trail." Phase 4 (Trust, Provenance, Forgetting) is explicitly chartered to build a "tamper-evident audit log" (hash-chained, append-only) and full provenance/lineage tracking. Phase 0 needs *some* form of `forget`, but building Phase 4's full audit-log machinery now would be scope creep the user explicitly flagged during planning.

## Decision

`forget` adds exactly two columns to `memories`: `deleted_at TIMESTAMPTZ NULL` and `deleted_reason TEXT NULL`. Calling `forget` sets both fields. `recall` and `search` filter `WHERE deleted_at IS NULL` by default. No separate audit-log table, no actor/diff tracking, no cryptographic tamper-evidence in Phase 0. `forget` is idempotent: a second call on an already-deleted record returns the existing `deleted_at` rather than raising an error.

## Rationale

Two nullable columns satisfy the charter's immediate non-negotiable ("no hard deletes... quarantine/archive with an audit trail" — the row itself, preserved and inspectable via direct `psql`, *is* the minimal audit trail for Phase 0) without building the append-only, hash-chained log that Phase 4 is specifically chartered to design properly (with real threat-model justification for its cryptographic properties). Building that now, before Phase 4's research pass, would mean guessing at a design that phase is meant to deliberately research.

Idempotency matters because `forget` may be retried by a client after a network hiccup — without it, a legitimate retry would surface as a spurious error.

## Alternatives considered

- **Full audit-log table now** (actor, old/new values, hash chain). Rejected: this is explicitly Phase 4 scope; building it now duplicates work once Phase 4's research determines the actual tamper-evidence requirements (e.g. Merkle-tree structure per MemLineage-style designs referenced in the Research Report).
- **Hard `DELETE FROM`.** Rejected outright — violates the charter's non-negotiable soft-delete standard.

## Consequences

- Phase 4 graduates from these two columns: the audit log it builds will reference `deleted_at`/`deleted_reason` as the base signal, extended with proper provenance chaining, not replacing them.
- Manual validation (`scripts/manual_recall_check.md`) explicitly verifies via direct `psql` that a "forgotten" row still physically exists with `deleted_at` set — proving the soft-delete contract end-to-end, not just at the unit-test level.
