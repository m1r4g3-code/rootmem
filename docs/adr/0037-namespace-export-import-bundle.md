# ADR 0037: Namespace export/import uses a versioned, verified bundle

**Status:** Accepted
**Date:** 2026-09-19

## Context

Identity continuity across deployments needs a way to move a namespace's memory. Nothing exists.

## Decision

A `PortabilityRepository` (Postgres and fake, one contract suite) exports a namespace's memories, entities, relations with belief state, memory-entity links, relation provenance and procedural memories into a versioned JSONL bundle with a manifest (counts, content SHA-256). Import recomputes the digest, refuses a mismatch, creates records in the target namespace with remapped ids, and appends one `import` audit entry carrying the bundle digest. Embeddings are excluded by default (derived data; existing backfill re-creates them). The audit log is not exported: it is a per-deployment chain, and importing foreign entries would break its meaning. It is an operator CLI action, not an MCP tool.

## Alternatives considered

- Raw database dump: rejected, not namespace-scoped and tied to the schema.
- Exporting the audit chain: rejected, see above.

## Consequences

Round-tripped memories get new ids and timestamps of import are new; original `created_at` is preserved in the record.
