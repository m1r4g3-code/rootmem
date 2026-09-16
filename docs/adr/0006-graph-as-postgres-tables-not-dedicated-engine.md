# ADR 0006: Bi-temporal semantic graph as plain Postgres tables — supersedes ADR 0001

**Status:** Accepted
**Date:** 2026-09-16
**Supersedes:** [ADR 0001](0001-graph-store-deferred-to-phase1.md)

## Context

ADR 0001 deferred choosing a graph store (named candidates: embedded KuzuDB or Postgres+AGE) because Phase 0 had no bi-temporal edge model to test either against, and explicitly named "Phase 1 kickoff" as "the forced re-evaluation point, not an indefinite deferral." Phase 1 now builds that model (entities and relations extracted from remembered content), so this ADR is that forced re-evaluation.

Fresh research this cycle found that both of ADR 0001's named candidates have separately become unsafe choices since it was written:

- **KuzuDB was archived in October 2025**, after Apple acquired the company behind it. Community forks (LadybugDB, Bighorn) exist but have no corporate backing and carry real abandonment risk.
- **Apache AGE has no official Windows support** — official docs assume Linux/WSL. A third-party fork (`ShanGor/apache-age-windows`) provides precompiled Windows binaries bundling AGE+pgvector+Postgres, but that's the same unofficial-binary risk class that already cost real development time with pgvector in Phase 0.

A third candidate neither Phase 0 document named was evaluated: **ArcadeDB** (Apache 2.0, actively maintained, positioned as the leading open-source Neo4j alternative in 2026). Its `arcadedb-embedded` Python package publishes real PyPI wheels for Windows x86_64, runs embedded in-process, and implements OpenCypher. A timeboxed spike (`scripts/spike_arcadedb_embedded.py`) actually installed and exercised it on this Windows Python 3.13 machine before this decision was finalized, rather than deciding from research alone.

**Spike findings:** install succeeded (real Windows wheel, ~64.5MiB, bundles its own Java 25 runtime via `jpype1` — no separate JVM install step) and it worked correctly on the first try — schema creation, vertex/edge insert, and a 1-hop Cypher query all behaved as expected. But cold start was expensive: `create_database` (first JVM touch) took 6.04s, and the first Cypher query took a further 3.01s — roughly 9 seconds before the graph is even queryable. Since Phase 0's ADR 0002 already committed to stdio transport, an MCP server is launched fresh as a subprocess by the client (Claude Code/Cursor) on every session start — a ~9-second tax on every single session start is a real, user-visible cost this spike made concrete rather than theoretical.

Separately, Phase 0's CI (`.github/workflows/ci.yml`) already runs Postgres+pgvector successfully on GitHub Actions' `ubuntu-latest` runners via Docker, every run, with zero WSL2/hypervisor exposure. The Docker/WSL2 failure that shaped so much of Phase 0's actual local-dev experience is a property of one physical developer laptop's hypervisor/BIOS — it does not apply to CI or to any real production deployment target.

## Decision

Model the bi-temporal semantic graph as plain Postgres tables — `entities`, `relations`, `memory_entities` — in the same database `memories` already lives in, queried via recursive CTEs for traversal. Do not adopt ArcadeDB, KuzuDB, or Apache AGE in Phase 1.

A contradiction between relations never deletes a row: it sets the losing relation's `valid_to` and `superseded_by`, and the winning relation's `supersedes` — a direct extension of ADR 0004's soft-delete philosophy to the graph layer.

**Concrete revisit trigger** (so this isn't a second silent deferral): reconsider a dedicated graph engine if recursive-CTE query plans become the measured bottleneck, or if a ranking term needs more than ~2-3 hop traversal — either of which would make the extra infrastructure's cost worth paying. Until then, the spike's findings stand as this project's only real data point on the question.

## Rationale

Once Postgres is already running in every environment that actually matters — CI, production, and (via a hosted instance, see ADR 0011) local dev — two more tables in the same database cost zero new infrastructure, zero new Windows-compatibility surface, and zero new cross-language binding risk. ArcadeDB's only decisive advantage over this — a demonstrated native-Windows install path — solves a problem (local-dev-machine compatibility) that doesn't generalize to CI or production, at the cost of a new runtime class (JVM-in-process) nothing else in this stack has exercised, with a measured, non-trivial per-session startup cost. Recursive CTEs are a well-understood, zero-dependency way to handle the shallow traversal depths (1-2 hops) Phase 1's exit criterion actually needs.

This also directly extends two decisions this project has already made and validated: ADR 0003's `Protocol`-based storage abstraction (a `GraphRepository` Protocol, additive, not a restructuring — exactly what ADR 0003's own Consequences section anticipated) and ADR 0004's soft-delete discipline (contradictions supersede, they don't delete).

## Alternatives considered

- **ArcadeDB-embedded.** Rejected for Phase 1 specifically because of the measured ~9-second cold-start cost landing on every MCP session start, plus the new JVM-runtime dependency class — not rejected as a technology in the abstract; the revisit trigger above keeps the door open once traversal needs actually outgrow recursive CTEs.
- **KuzuDB.** Rejected — archived, orphaned, real abandonment risk for a new dependency.
- **Apache AGE (official or the `apache-age-windows` fork).** Rejected — no official Windows support, and the community fork carries the same unofficial-binary risk class pgvector's own Windows gap already demonstrated is real.

## Consequences

- `storage/graph_protocols.py` defines `GraphRepository` as a new, separate Protocol from `MemoryRepository` (different aggregate, different lifecycle semantics — bi-temporal validity, not soft-delete-via-single-timestamp). Two implementations (`PostgresGraphRepository`, `InMemoryGraphRepository`) verified against a shared contract-test suite, exact parity with the `MemoryRepository`/`contract.py` pattern.
- `scripts/spike_arcadedb_embedded.py` and `scripts/spike_pgvector_windows_build.md` are kept in the repo (not deleted) as the real evidence this decision and ADR 0011 are based on, for whichever future phase revisits either question.
- If the revisit trigger fires in a later phase, the `GraphRepository` Protocol boundary means swapping the Postgres-tables implementation for a dedicated engine requires a new implementation behind the same interface, not a restructuring — the same story ADR 0001 already told about deferring this decision from Phase 0 to Phase 1.
