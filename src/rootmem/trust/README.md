# trust

Reserved for Phase 4: provenance/trust scoring with staleness decay,
type-isolation, and the tamper-evident audit log. Phase 0's `forget` only
sets `deleted_at`/`deleted_reason` (ADR 0004) — the full audit trail this
module will build graduates from those two columns.
