# Phase 0 Research Memo — Foundations

**Phase:** 0 — Foundations
**Date:** 2026-09-13
**Inputs:** ROOTMEM Research Report, ROOTMEM Build Reference (both provided in full at project kickoff)

## Scope of this memo

Phase 0's exit criterion, per the Build Reference, is narrow: *an agent remembers a fact across two separate sessions via MCP.* This memo extracts only what that exit criterion actually requires from the two source documents, rather than re-deriving the whole project's research base. Later phases each get their own research memo scoped to what they add.

## What the source documents establish that Phase 0 must respect

1. **MCP is the correct integration surface to build first.** Both documents agree MCP (Model Context Protocol) has become the de facto standard for agent-tool integration in 2026, and that shipping the MCP server before a REST API or framework adapters gives the widest reach for the least effort. This directly justifies Phase 0 building only an MCP server, no REST API yet (Build Reference §2.1, §4.G; Research Report §5).

2. **Storage engine choice: Postgres+pgvector, not a second vector DB.** The Build Reference explicitly recommends Postgres+pgvector over Qdrant/LanceDB/Weaviate specifically to avoid running two databases, and the same logic applies to the graph layer (Postgres+AGE or embedded KuzuDB instead of standing up Neo4j). Phase 0 only needs the episodic/fact store, not the graph, so only Postgres+pgvector is provisioned now (see ADR 0001 for the graph-deferral reasoning).

3. **No product does real consolidation, provenance, or procedural memory well — but Phase 0 doesn't need to solve any of that yet.** The Build Reference's competitive-gap analysis (§3) is what justifies later phases (consolidation, trust/provenance, procedural memory), not Phase 0. It matters here only insofar as it explains *why* the schema must be forward-compatible (schema_version, provenance fields) without Phase 0 building the machinery that will eventually use them — see the Requirements doc's "forward-compatibility, not feature-completeness" principle.

4. **Benchmarks are saturated/self-reported and not a Phase 0 concern.** LoCoMo/LongMemEval scores are explicitly called out as unreliable (Vectorize.io measured Mem0 at 49% vs. its self-reported 94.4%). Phase 0 has no retrieval-ranking sophistication to benchmark against MemoryAgentBench or Vectorize AMB — those harnesses become meaningful starting Phase 1 (real extraction) and especially Phase 2 (consolidation) and Phase 4 (trust-weighted ranking). Phase 0's own "benchmark" step is therefore just baseline latency measurement, not a competitive eval.

5. **Global engineering standards apply from commit one**, per the project charter: type safety, schema versioning, attributable writes, soft-delete-only, idempotency, structured observability, config-over-code, and Docker-independent unit testability. None of these are Phase-0-specific research findings — they're charter-level constraints restated as Phase 0 requirements (see `phase0-requirements.md`).

## What Phase 0 explicitly does NOT need from the source documents yet

- The decay/salience/retrieval-ranking baseline formulas (Build Reference §5, steps 9 and 18) — these presuppose a consolidation engine and trust scores that don't exist until Phase 2/4. Reading them now would produce speculative math with nothing real to fit (see `docs/math-spec/phase0-math-spec.md`).
- The competitor system-by-system technical breakdown (Mem0, Letta, Zep, MemOS, Cognee, MIRIX) — relevant to differentiation strategy in Phase 1+ (extraction fidelity, consolidation design), not to standing up a bare MCP server.
- SKILL.md / procedural memory research — Phase 3.
- Cross-instance identity continuity literature — Phase 4/5, explicitly frontier work.

## Open questions carried forward to Phase 1's research memo

- Which embedding model (Voyage voyage-3 vs. voyage-3-lite vs. voyage-3-large) to fix `content_embedding`'s dimension to, and the ivfflat/hnsw indexing strategy that follows from that choice.
- Graph store choice (embedded KuzuDB vs. Postgres+AGE) — deferred from Phase 0 per ADR 0001, must be decided before Phase 1's bi-temporal semantic graph work begins.
- Extraction-fidelity trade-offs (Haiku bulk extraction vs. Sonnet for ambiguous cases) — not yet relevant since Phase 0 has no extraction pipeline at all (writes come directly from explicit `remember` tool calls, not inferred from conversation).

## Retrospective feed-forward

This section will be filled in `docs/retro/phase0-retro.md` after Phase 0 ships, and its findings become an input to Phase 1's research memo, per the charter's chained SDLC.
