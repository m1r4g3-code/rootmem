# Phase 4 Requirements & Constraints — Ranking, Decay, Trust & Tamper-Evident Audit Log

## Exit criterion

> In one namespace, via MCP alone:
> **(a)** two memories of similar relevance, one repeatedly accessed and one stale (time injected through a clock parameter, no sleeping): `search` ranks the reinforced one first and returns a per-term score breakdown;
> **(b)** a memory from a high-trust source outranks an equal-relevance memory from a low-trust source; a skill with reported successes outranks an equal skill with reported failures in `find_skill`;
> **(c)** a memory linked to the queried entity is lifted by `graph_proximity`;
> **(d)** every remember/update/forget/feedback/consolidate/supersede in the scenario appears in the audit log and `verify_audit` returns valid;
> **(e)** after one `audit_log` row is altered directly in Postgres, `verify_audit` reports the first tampered row;
> **(f)** forgotten memories never surface, and decay never deletes anything.

Gate for tagging `v0.4.0-phase4`: one automated exit-criterion test plus one live manual pass (`scripts/manual_phase4_check.md`).

## Functional requirements

- FR1: pure `retrieval/decay.py`: `retention(...) -> [0,1]`.
- FR2: `memories` gains `last_accessed_at`, `access_count` (trust is computed at rank time from source and confidence, not cached); `MemoryRepository.record_access(ids, now)`; `recall` and `search` hits record access.
- FR3: pure `trust/scoring.py`: `memory_trust(source, confidence, params)`; per-source reliability map in `Settings`.
- FR4: pure `retrieval/ranking.py::rank_score(...)` returning a per-term breakdown; missing terms are neutral and weights renormalize.
- FR5: `search` over-fetches candidates and re-ranks; `SearchResultItem` exposes the breakdown. `find_skill` re-ranks with effectiveness.
- FR6: `graph_proximity` from `memory_entities` links plus 1-hop neighbours of the entity named in the query.
- FR7: `procedural_memories` gains `applied_count`, `success_count`; new `report_skill_outcome` tool updates a Beta posterior via `apply_evidence`.
- FR8: `audit_log` append-only table, per-namespace hash chain, DB trigger rejecting UPDATE/DELETE; `AuditLogRepository` Protocol with Postgres and in-memory implementations.
- FR9: `audit/chain.py`: `compute_hash`, `verify_chain` (pure). New `verify_audit` MCP tool.
- FR10: audit rows recorded for every mutating tool path and consolidation writes.
- FR11: heavy SDK imports made lazy; handshake re-measured.

## Non-functional requirements

- NFR1: search latency stays the same order of magnitude (re-rank is O(candidates); one batched access update, one graph lookup).
- NFR2: `mypy --strict`, zero suppressions; scoring/decay/chain logic pure and unit-testable.
- NFR3: decay is read-time only and never mutates or deletes (ADR 0004).
- NFR4: no new dependency (hashlib only), no new service.
- NFR5: all tunables in `Settings`, fail-fast, documented provisional.
- NFR6: a mutation whose audit append fails is reported as an error, never silently unaudited.

## Non-goals

Cross-instance identity; REST/remote transport; learned/bandit ranking; automatic forgetting; Merkle tree, signing, external anchoring; benchmark harness (ADR 0026); new graph engine; new worker infra.
