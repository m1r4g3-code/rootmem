# Phase 1 Requirements & Constraints — Semantic Graph, Vector Retrieval & Extraction

## Exit criterion

> Given two session transcripts submitted through the capture/extraction pipeline, where the second states a fact contradicting one established in the first (same entity, same predicate, different object — e.g. "Alice works at Acme Corp" then later "Alice joined Globex as an engineer"), the system must, end-to-end and via MCP:
>
> **(a)** extract entities and relations into the graph store, each relation linked back to its source `memories` row;
> **(b)** detect the new relation conflicts with the currently-active `(Alice, works_at)` one, and resolve it by setting the old relation's `valid_to` and recording a `supersedes` link — never deleting or overwriting the old row;
> **(c)** answer a semantic-only query with no lexical overlap with either stored sentence (e.g. "where is Alice employed now") by returning the current fact ranked above the superseded one and above unrelated memories — proven by also running the identical query through full-text-only search and showing it fails or scores worse, demonstrating the vector component does real work rather than riding lexical coincidence; and
> **(d)** a `related` MCP tool call against the `Alice` entity returns both the current and superseded relations with correct `valid_from`/`valid_to`, proving the bi-temporal history persisted rather than being overwritten.

This is the single pass/fail gate for tagging `v0.1.0-phase1`, validated by one automated integration test (`tests/integration/test_phase1_exit_criterion.py`) and one manual dogfooding pass recorded in `scripts/manual_phase1_check.md` — the same dual automated+manual sign-off ritual Phase 0 used.

## Functional requirements

- FR1: `remember` populates `content_embedding` via a real embedding model call at write time; on embedding-provider failure, the write still succeeds with `content_embedding = NULL` (graceful degradation, not a blocked write).
- FR2: `search` gains a `mode` parameter (`"text"` | `"semantic"` | `"hybrid"`, default `"hybrid"`) — `"semantic"` ranks by cosine similarity against the query embedding alone; `"hybrid"` blends text rank and cosine similarity; `"text"` preserves Phase 0's exact prior behavior.
- FR3: A new `ingest_session` MCP tool accepts a session transcript and runs it through capture → extraction → graph write, returning a summary of entities/relations extracted and any contradictions resolved.
- FR4: A new `related` MCP tool returns entities/relations connected to a named entity, up to `max_hops` (default 1), including superseded (non-active) relations with their `valid_from`/`valid_to`.
- FR5: The extraction pipeline detects contradictions — a new relation for an already-active `(subject, predicate)` pair — and resolves them deterministically: the most recent `valid_from` wins when its confidence exceeds `contradiction_confidence_floor`; otherwise both relations are marked `metadata.contested = true` rather than one being silently chosen.
- FR6: Superseding a relation never deletes or overwrites the losing row — it sets `valid_to`, `superseded_by` on the loser and `supersedes` on the winner, mirroring `forget`'s soft-delete discipline (ADR 0004) at the graph layer.
- FR7: Entity resolution within a `(namespace, entity_type)` pair uses exact normalized-name matching (case-folded, whitespace-collapsed) — deliberately minimal, not fuzzy/coreference-aware (see the research memo).
- FR8: `capture/cli.py` provides a command-line entrypoint for batch/hook-triggered ingestion, independent of any running MCP session, so a client-side `SessionEnd`-style hook can shell out to it.

## Non-functional requirements

- NFR1 (embedding latency budget): a single `remember` call's added embedding-provider round-trip should not push total tool latency past ~2s under normal conditions — a sanity budget, not a tuned SLA, to catch gross regressions (e.g. accidental batching of one item into a slow path).
- NFR2 (external-API failure isolation): a Voyage or Anthropic API outage must degrade the specific dependent operation (embedding population, extraction) without crashing the MCP server process or corrupting `memories`/graph state — same "fail the one thing, not the process" discipline as Phase 0's `StorageError` handling.
- NFR3 (type safety): `mypy --strict` continues to pass with zero errors, zero suppressions, across all new modules (`embedding/`, `extraction/`, `capture/`, the graph storage layer).
- NFR4 (testability): all new business logic (contradiction resolution, the extraction pipeline, capture orchestration) is unit-testable against fakes with zero external-API or Docker dependency; the embedding fake is fixture-replay (real recorded Voyage embeddings), not naive hashing, so similarity-ranking tests exercise genuine semantic structure rather than a fake's incidental behavior (see ADR 0009).
- NFR5 (schema discipline): the graph tables (`entities`, `relations`, `memory_entities`) follow `memories`' existing conventions — UUID primary keys, `namespace` scoping, `DOUBLE PRECISION` (never `REAL`) for any stored confidence value (Phase 0 already paid for this lesson once, see ADR 0004/`docs/retro/phase0-retro.md`), and never a hard `DELETE`.
- NFR6 (cost control): real-API integration tests (actual Voyage/Anthropic calls) run in a separate, sparse CI job gated behind repo secrets, not on every push — this phase introduces the project's first per-run monetary cost, which must not silently attach to the existing free, deterministic CI job.
- NFR7 (config): all new external-API keys and tunables (`voyage_api_key`, `anthropic_api_key`, `voyage_model`, `voyage_output_dimension`, `extraction_model`, `hybrid_search_weight_text`/`hybrid_search_weight_vector`, `contradiction_confidence_floor`) load via the existing `pydantic-settings` `Settings` class, fail-fast at startup — no new config mechanism introduced.
- NFR8 (layer isolation): the storage layer (`storage/`) never imports `voyageai` or `anthropic` directly — embedding and extraction are separate Protocol-based ports (`EmbeddingProvider`, `ExtractionProvider`), consistent with the charter's layer-isolation mandate already cited in ADR 0003.

## Explicit non-goals for Phase 1

Consolidation/"sleep cycle" and salience scoring (Phase 2); decay/forgetting curves, trust/provenance scoring, the multi-factor retrieval-ranking formula, and the tamper-evident audit log (Phase 4); procedural memory/SKILL.md (Phase 3); cross-instance identity continuity (Phase 4/5); REST API/remote MCP transport (Phase 5+); an HTTP webhook listener (capture is CLI + MCP-tool only — see ADR 0010); full Bayesian contradiction resolution (deterministic rule now — see ADR 0008); sophisticated entity resolution/coreference (exact normalized-name match only); ArcadeDB or any dedicated graph engine (spiked and evaluated per ADR 0006, not adopted). These are non-goals, not deferred requirements to sneak in early.

## Traceability to charter global standards

| Charter standard | How Phase 1 satisfies it |
|---|---|
| Type safety everywhere | `mypy --strict` CI gate, extended to all new modules |
| Schema versioning from day one | Graph tables follow `memories`' existing `schema_version` convention where applicable |
| Every write is attributable | Every `relations` row carries `source_memory_id` linking back to the `memories` row it was extracted from |
| Every destructive operation is soft | Contradiction resolution sets `valid_to`/`superseded_by`, never deletes (FR6) |
| Idempotency by default | Entity resolution's exact-match dedup means re-ingesting the same transcript resolves to the same entities rather than duplicating them |
| Observability from first commit | Embedding/extraction calls logged via the existing `observability/metrics.py` pattern, including provider failures |
| No unbounded LLM calls | Extraction runs once per `ingest_session`/capture-CLI invocation, not in a retry loop; `extraction_max_tokens_per_call` bounds each call |
| Config over code | All new tunables in `pydantic-settings`, per NFR7 |
| Everything testable in isolation | `GraphRepository`, `EmbeddingProvider`, `ExtractionProvider` Protocols, each with a fake, per NFR4 |
