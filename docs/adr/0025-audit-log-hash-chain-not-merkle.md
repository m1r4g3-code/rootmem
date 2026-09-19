# ADR 0025: The audit log is an append-only per-namespace hash chain, not a Merkle tree

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR 0004 chartered a tamper-evident audit log. ROOTMEM is a single-node store.

## Decision

`audit_log` rows commit to the previous row's hash with SHA-256. A DB trigger rejects UPDATE and DELETE. `verify_audit` recomputes the chain and reports the first broken row. Rows are recorded at the tool and consolidation layer, and an append failure fails the operation.

## Alternatives considered

- Merkle tree, signing or external anchoring: deferred. Revisit if multi-party verification or inclusion proofs are needed.
- Editing every repository to emit audit rows: rejected, wide blast radius.

## Consequences

The chain detects tampering after the fact; it does not prevent a database superuser from rewriting the whole chain. That limit is stated, not hidden.
