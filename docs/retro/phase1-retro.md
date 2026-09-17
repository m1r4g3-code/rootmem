# Phase 1 Retrospective — Semantic Graph, Vector Retrieval & Extraction

**Status:** Filled in after `v0.1.0-phase1`'s automated exit-criterion test, full unit/integration suites, and a live manual dogfooding pass through a real Claude Code session all passed on 2026-09-17.

Per the charter's chained SDLC, these findings are an explicit input to Phase 2's research memo — Phase 2 owns real Bayesian contradiction math, salience, and consolidation, several of which this phase deliberately deferred with a named revisit trigger.

## What shipped

- Graph store as three plain Postgres tables (`entities`, `relations`, `memory_entities`) rather than a dedicated graph engine — ADR 0006, superseding ADR 0001.
- `voyage-4` embeddings truncated to 1024 dimensions, HNSW index with `vector_cosine_ops` (ADR 0007).
- Deterministic contradiction resolution: most-recent-`valid_from` wins above a confidence floor, else both sides flagged `contested` (ADR 0008) — real Bayesian math explicitly deferred to Phase 2.
- `EmbeddingProvider`/`ExtractionProvider` Protocols (ADR 0009), each with a real adapter (Voyage, Anthropic Haiku-tier) and a fake (fixture-replay for embeddings, scripted for extraction).
- `capture/` module: CLI entrypoint + MCP `ingest_session` tool, no HTTP webhook listener (ADR 0010).
- `search`'s default mode changed to `"hybrid"` (text + vector blend via `retrieval/ranking.py`'s provisional `hybrid_score`), with `"text"`/`"semantic"` also selectable.
- Two new MCP tools (`related`, `ingest_session`), bringing the server to 7 tools total.
- A sparse, secret-gated real-API CI job (Voyage + Anthropic), separate from the free Docker-only job, triggered on tags/manual dispatch only.
- `tests/integration/test_phase1_exit_criterion.py` — the automated proof of the full contradiction → graph-history → semantic-search scenario, end-to-end via the real MCP protocol, real Postgres, real Voyage, real Anthropic.
- A live manual dogfooding pass (`scripts/manual_phase1_check.md`), executed today through a real Claude Code session, all 5 checklist items confirmed.

## What worked

- **Contract-test parity caught a real bug.** `GraphRepository.related()`'s Postgres recursive-CTE implementation was initially looser than the in-memory fake's frontier-by-frontier BFS (it included a relation if either endpoint was anywhere within `max_hops` via *any* path, not strictly `< max_hops`). The shared contract suite (`graph_contract.py`) failed against real Postgres and caught it immediately — exactly the parity guarantee ADR 0003 was designed to provide, now proven to hold for a second, structurally different Protocol.
- **Fixture-replay embeddings gave genuine semantic-structure tests without paying for API calls on every run.** Recording real Voyage vectors once (`tests/fixtures/voyage_embeddings.json`) and replaying them offline meant unit tests could assert real similarity relationships, not just "a vector came back."
- **Layer isolation (ADR 0009) held.** Storage code never imports `voyageai`/`anthropic` anywhere — confirmed by grep, not just by convention — even after wiring the graph and embedding layers together.
- **Graceful degradation (NFR2) worked under a real failure, not just a mocked one.** During today's live dogfooding pass, the first three `ingest_session` calls all came back `embedded: false` because this Voyage account (free tier, no payment method, 3 requests/minute) was still rate-limited from the test suite runs immediately before. Extraction and contradiction resolution kept working correctly regardless — the write never blocked or failed, exactly as designed. This is a stronger proof than any unit test could give, since it was an unplanned, real trigger of the failure path.

## What didn't work / surprises

- **Predicate and entity-type casing inconsistency, found only via real LLM calls.** The extraction system prompt initially let the model choose synonymous predicates ("joined" vs "works_at") and inconsistent entity-type casing ("Person" vs "person") across mentions — both would silently break the exact-string contradiction/lookup comparisons downstream. No fake or scripted test could have caught this; it only surfaced against the real Anthropic API. Fixed at two levels: a tightened prompt (defense in depth) and, for entity type specifically, structural normalization (`normalize_entity_type()`) so a prompt regression can't reintroduce the bug.
- **Voyage's free-tier 3-requests/minute cap is a real, hard constraint**, not just a test artifact — it fired during automated testing (requiring `max_retries=3` plus deliberate pacing in the exit-criterion test) *and* during today's live dogfooding pass. Any production deployment on a free-tier key needs to budget for this explicitly rather than assume embedding is instant.
- **A genuine MCP server startup-latency bug, found only by attempting the live manual dogfooding pass.** `main_async` constructed `VoyageEmbeddingProvider` and `AnthropicExtractionProvider` eagerly, before starting the stdio transport. On this Windows machine, `import voyageai` alone measured ~12s (a one-time-per-process cost the first time anything pulls in the `httpx`/`httpcore`/`certifi` chain — not a network call), pushing total startup to 27–57s across repeated measurements — past Claude Code's ~30s MCP connection timeout. The client showed "Connection closed"/"Failed" with the server never even completing the handshake. Fixed by constructing both providers (import included, not just the constructor call) in a background thread, awaited lazily on first real use, so `run_stdio_async()` starts accepting the handshake almost immediately. Handshake now completes in ~18.7s consistently. This is the single strongest argument in this phase for why the manual dogfooding pass earned its place even though the automated exit-criterion test was already green: the automated test drives the server via a Python test harness with no realistic timeout expectation, so it never would have caught a client-side connection-timeout failure mode.
- **`search` has no awareness of graph supersession state** — a real architectural gap, not a bug, found while writing the exit-criterion test: ranking a superseded fact against the current one requires connecting the `memories`-table search to the `relations`-table's currency, which nothing in Phase 1 wires up (that's explicitly Phase 4's multi-factor ranking-formula scope). Resolved for this phase by restructuring the exit-criterion test to prove semantic-vs-text search on an *independent* fact instead of the contradiction pair, and relying on `related` (which does track currency correctly) to prove supersession — an explicit, user-approved scope decision, not a silent gap.
- **pgvector has no native-Windows build path** on this machine (no VS C++ toolchain) — worked around with Neon-hosted Postgres for local dev rather than Docker, mirroring Phase 0's native-Postgres fallback for the same underlying Windows/Docker constraint.
- **The ArcadeDB spike's numbers concretely validated the "plain Postgres tables" call**: 6.04s to create an embedded database and 3.01s for the first query — real JVM cold-start cost that a dedicated graph engine would have introduced for no benefit at Phase 1's scale.
- **Process gap noticed in passing**: `docs/retro/phase0-retro.md` was never actually filled in — it's still the unfilled template from Phase 0's initial scaffolding commit. Phase 1's research memo therefore didn't have real Phase 0 retro findings to draw on, only the plan document's own carried-forward open items. Worth deciding whether to backfill it or explicitly accept the gap before Phase 2 kicks off.

## Decisions to revisit in Phase 2

- Real Bayesian contradiction math, replacing the deterministic most-recent-wins rule — Phase 1 punted this explicitly, and real retrieval-outcome data now exists to calibrate against.
- Entity resolution beyond exact normalized-name match within `(namespace, entity_type)` — nicknames and coreference are unhandled and will misfire as this scales past toy examples.
- `hybrid_score`'s weights are a flat, provisional 0.5/0.5 linear blend (`docs/math-spec/phase1-math-spec.md`) — revisit once there's real query/relevance data, not before.
- Whether `search` should become graph-aware (rank by supersession currency, not just content similarity) — explicitly named as Phase 4 scope now, but worth confirming that's still the right phase for it once Phase 2/3 priorities are clearer.
- Postgres pool creation in `main_async` is still eager (blocking, ~5-9s observed) — comfortably under the connection timeout today, so left alone, but if a future dependency makes pool setup slower, the same lazy-background-thread pattern used for the embedding/extraction providers is the template to reach for.

## Metrics captured

- MCP handshake latency: 27-57s before the startup-latency fix (varying with OS-level first-import cost); ~18.7s consistently after.
- `tests/integration/test_phase1_exit_criterion.py` wall time: 81.90s, including a deliberate 35s rate-limit-pacing sleep.
- ArcadeDB spike: 6.04s `create_database`, 3.01s first query (embedded JVM cold start).
- Raw Neon Postgres connection time: 4.6-9.4s observed across multiple runs (serverless cold-start variance).
- `import voyageai` alone: ~12s on first touch per process on this machine; `import anthropic` immediately after: ~0.1s (shares the already-warmed httpx/certifi chain).
