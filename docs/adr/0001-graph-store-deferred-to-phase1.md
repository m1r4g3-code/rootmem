# ADR 0001: Defer the semantic graph store to Phase 1

**Status:** Accepted
**Date:** 2026-09-13

## Context

The Build Reference's literal Phase 0 steps say "stand up Postgres+pgvector, Redis, embedded graph (KuzuDB or Postgres+AGE)." The Research Report recommends Postgres+AGE or embedded KuzuDB over a standalone Neo4j/FalkorDB server to avoid running a second database. Phase 0's actual exit criterion, however, is narrower: an agent remembers a fact across two sessions via MCP — which is fully satisfiable with a single Postgres+pgvector table.

## Decision

Do not provision a graph store (KuzuDB or Postgres+AGE) in Phase 0. Defer it to Phase 1, when the bi-temporal semantic graph is actually designed and built.

## Rationale

Standing up a graph store that no Phase 0 code touches and no Phase 0 test exercises is not the kind of infrastructure discipline the charter asks for — it's unverified infrastructure that can silently drift (version mismatches, broken container config) for the weeks between Phase 0 and Phase 1 kickoff, with nothing catching the drift because nothing uses it. The charter's own standard — "everything is testable in isolation," "no component may require the full stack running to unit-test its core logic" — argues for provisioning infrastructure when there's real behavior to test against it, not preemptively.

The storage layer's repository Protocol pattern (ADR 0003) already guarantees this deferral costs nothing later: adding a `GraphRepository` in Phase 1 is a new module under `storage/graph/`, not a restructuring of anything Phase 0 builds.

## Alternatives considered

- **Stand up KuzuDB now, per the literal Build Reference wording.** Rejected: violates the "no unverified infrastructure" principle above: an idle graph DB with zero code paths through it for a full phase.
- **Stand up Postgres+AGE now** (same Postgres instance, extension only). Slightly cheaper than a second embedded engine, but still zero code touches it in Phase 0 — same objection applies.

## Consequences

- Phase 1's research memo must explicitly revisit this decision — this ADR names Phase 1 kickoff as the forced re-evaluation point, not an indefinite deferral.
- No migration or schema cost is paid now for the graph choice; it is decided when there's a concrete bi-temporal edge model to test against it.
