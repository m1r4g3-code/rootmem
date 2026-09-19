# Phase 3 Retrospective — Procedural Memory, Failure→Lesson Distillation & SKILL.md

**Status:** Filled in after `v0.3.0-phase3`'s automated exit-criterion test (1 passed, 428.75s), full unit suite (181 passed), ruff and `mypy --strict` clean, and a live manual dogfooding pass (7/7, including a full client restart) on 2026-09-19.

This is an input to Phase 4's research memo (decay, trust/provenance scoring, multi-factor ranking, tamper-evident audit log).

## What shipped

- Episodic→procedural (skill) and failure→lesson distillation inside the same consolidation pass as episodic→semantic (ADR 0020); one `consolidation_runs` row now reports `facts_distilled`, `procedures_distilled`, `lessons_distilled`.
- Session-trace clustering (ADR 0017): episodes grouped by `(source_session_id, session_outcome)`, one embedding per trace, Phase 2's `cluster_by_similarity` reused unmodified.
- Explicit `session_outcome` on `ingest_session` (ADR 0019).
- `procedural_memories` + provenance tables (migrations 0005, 0006), `ProceduralMemoryRepository` and `ProceduralDistillationProvider` Protocols with fake and real (Postgres / Anthropic) implementations.
- SKILL.md-conformant rendering (`consolidation/skill_format.py`), served via `get_skill`, never written to disk (ADR 0018).
- `find_skill` and `get_skill`; the server now exposes 11 MCP tools.
- Exit criterion scoped to an MCP-native proof, not SWE-bench/Terminal-Bench (ADR 0021).

## What worked

- **Spike margin was large.** Matching successful-trace pair 0.9364 vs next-closest 0.4272 (margin ~0.51), versus Phase 2's 0.005. Session grouping is a much stronger signal than flat episode similarity.
- **Real-Postgres contract tests caught real bugs again** (fourth phase running): supersede ordering, and a ts_rank noise issue (below).
- **Graceful degradation held under live rate limiting.** During the manual pass, Voyage's 3 req/min cap degraded one ingest to `extraction_degraded` and one to `embedded: false`; episodes were still stored and consolidation succeeded.
- **Live results:** one consolidate pass gave 1 fact, 1 procedure, 1 lesson; `find_skill` in the user's own words ranked the skill first (0.402); the lesson query returned the lesson (0.366); the skill survived a client restart with identical score and content.

## What didn't work / surprises

- **Deferrable-FK vs partial-unique-index conflict on supersede.** Inserting the new row first violated the partial unique index on active names; updating the previous row first violated the `superseded_by` FK. Fix: client-generated id, UPDATE-first, and migration 0006 making the FK `DEFERRABLE INITIALLY DEFERRED`.
- **ts_rank epsilon, including a latent Phase 1 bug.** Non-matching rows returned ~1e-20 scores rather than 0, so they appeared as hits. Reproduced in isolation and fixed with `WHERE score > 1e-9` in both `search_hybrid` implementations, which also fixed the same latent issue in Phase 1's memory search.
- **A requirements-wording category error, caught while writing the exit-criterion test.** Requirement (d) said the skill must outrank raw episodic memories, but `find_skill` searches only `procedural_memories`, so that comparison is structurally impossible. Reworded (skill ranks above the unrelated lesson; the domain exclusion is itself the proof). Third time in this project that writing the test, not the implementation, found the real issue.
- **Startup latency headroom.** After the Phase 3 changes the first restart timed out (`CONNECT_TIMEOUT`, 30s). Measured handshake 12.3s, of which ~9s is the cold `mcp` import; a `/mcp` reconnect worked. Three lazy providers plus imports leave less headroom under the client's 30s limit than before. Watch item for Phase 4.
- **Inline auto-trigger ordering (carried from Phase 2).** The first `ingest_session` into a fresh namespace still consumes that episode solo. Both the exit-criterion and manual checks order ingests so no session trace is split. Now known to also affect skill induction, not just fact clustering.

## Decisions to revisit in Phase 4

- **Batch scoping limitation:** a session straddling two consolidation passes is not grouped as one trace. Revisit only if real usage shows it matters.
- `procedural_session_similarity_threshold=0.80` and `procedural_min_recurrence=2` are validated on a synthetic set only.
- Startup latency: consider lazier imports if the handshake budget tightens.
- Skill effectiveness/usage tracking and trust scoring were explicit Phase 4 non-goals here.
- Whether a real benchmark harness (ADR 0021's revisit trigger) is warranted.

## Metrics captured

- Exit-criterion test wall time: 428.75s (mostly deliberate 35s pacing sleeps for Voyage's 3 req/min cap).
- Unit suite: 181 passed in 4.17s. mypy --strict: 121 source files clean.
- Spike: 0.9364 matching vs 0.4272 next-closest at threshold 0.80.
