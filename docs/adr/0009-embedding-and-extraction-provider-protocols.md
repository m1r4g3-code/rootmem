# ADR 0009: `EmbeddingProvider` and `ExtractionProvider` as separate Protocols; fixture-replay, not naive fakes

**Status:** Accepted
**Date:** 2026-09-16

## Context

Phase 1 introduces the project's first two external-LLM-API dependencies (Voyage for embeddings, Anthropic for extraction). ADR 0003 already established the storage layer must never import a concrete driver directly, and its Consequences section explicitly anticipated this moment: "Adding the Phase 1 embedding-backed semantic search or the Phase 1 graph store means adding new Protocol methods or new Protocol interfaces respectively." Embedding and extraction are a different kind of dependency than storage, though — they're calls to external LLM APIs, not a database — so the charter's layer-isolation mandate (cited in ADR 0003) requires the storage layer not reach out to Voyage/Anthropic itself.

Separately: Phase 1's exit criterion depends on proving *real* semantic similarity ranking (a query with no lexical overlap with either stored sentence must still rank the right fact first). A naive fake embedding provider (e.g. a hash of the input text) has no real semantic structure — it could make the exit-criterion test pass or fail for reasons unrelated to whether the actual system works, which would defeat the point of testing it at all.

## Decision

Two new, narrow Protocols, each with a real and a fake implementation:

- **`EmbeddingProvider`** (`embedding/protocols.py`): `async def embed(self, texts: list[str]) -> list[list[float]]`. Real: `VoyageEmbeddingProvider`. Fake: a **fixture-replay provider**, not a naive stub — `tests/fixtures/voyage_embeddings.json` holds real Voyage embeddings for a fixed sentence set, recorded once and replayed offline in unit tests.
- **`ExtractionProvider`** (`extraction/protocols.py`): `async def extract(self, text: str, context: ExtractionContext) -> ExtractionResult`. Real: `AnthropicExtractionProvider` (Haiku-tier, tool-calling for structured JSON). Fake: `ScriptedExtractionProvider`, returning canned entity/relation sets for pipeline and contradiction-logic unit tests, isolated from LLM nondeterminism.

Neither Protocol lives in `storage/` — `capture/ingest.py` takes both, plus `MemoryRepository` and `GraphRepository`, as constructor-injected parameters, the same dependency-injection shape `remember.py` already established for `MemoryRepository` in Phase 0.

## Rationale

Fixture-replay for embeddings is the load-bearing decision here: it lets unit tests exercise genuine cosine-similarity behavior (real semantic structure, recorded once from the real model) with zero network calls, zero API cost, and zero flakiness from a live API — while still meaning a passing similarity-ranking test is evidence the *real* embedding space behaves as expected, not just evidence a fake's incidental behavior happens to satisfy an assertion. A naive fake couldn't offer that guarantee at any price.

Extraction doesn't get the same fixture-replay treatment because its output (structured entity/relation JSON) isn't something a "replay" meaningfully validates the same way — a scripted fake that returns known, hand-picked entity/relation sets is sufficient for testing the pipeline and contradiction logic in isolation, since the actual quality of LLM-driven extraction isn't what those tests are meant to prove (that's what the real-API integration tests and the manual exit-criterion validation are for).

## Alternatives considered

- **A single combined Protocol for both.** Rejected: embedding and extraction have unrelated interfaces, failure modes, and testing strategies (fixture-replay vs. scripted) — combining them would force one test-double strategy to serve two needs it doesn't fit.
- **Naive hash-based embedding fake.** Rejected: has no real semantic structure, so a similarity-ranking test passing against it proves nothing about whether real semantic search works.
- **Mocking the Voyage/Anthropic SDK client objects directly.** Rejected, same reasoning ADR 0003 already gave for rejecting mocked `asyncpg` calls: brittle, tests implementation details (which SDK methods get called) rather than behavior.

## Consequences

- `tests/fixtures/voyage_embeddings.json` is checked into the repo — a small, fixed set of real embeddings, not regenerated per test run, so unit tests stay deterministic and fast.
- The real-API integration tests (gated CI job, NFR6 in `docs/requirements/phase1-requirements.md`) are what actually exercise `VoyageEmbeddingProvider`/`AnthropicExtractionProvider` against the live APIs — the fixture-replay/scripted fakes intentionally don't claim to substitute for that.
- Exact extraction model ID is pinned at implementation time by checking actual availability, not guessed in advance — the same discipline ADR 0002 established when the assumed `FastMCP` class name turned out to be pre-2.x naming.
