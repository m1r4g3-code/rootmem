# capture

The ingestion layer that feeds the extraction pipeline — `remember` is
still the only *explicit* write path (an agent stating a fact directly),
this is the *inferred* one (a transcript run through embedding + LLM
extraction).

- `ingest.py` — `ingest_transcript`, the orchestration: embed (graceful
  degradation on failure), store as a `memories` row, extract entities/
  relations, materialize them into the graph. Dependency-injected against
  `MemoryRepository`/`GraphRepository`/`EmbeddingProvider`/
  `ExtractionProvider`, fully unit-testable against fakes
  (tests/unit/capture/test_ingest_fake_backend.py).
- `cli.py` — the CLI entrypoint a client-side hook shells out to (ADR
  0010 — deliberately not an HTTP webhook listener). See
  `docs/capture-hook-example.md` for wiring it to Claude Code's own
  `hooks.json`.
- The `ingest_session` MCP tool is the in-session equivalent, for batch
  import without leaving an active MCP conversation.
