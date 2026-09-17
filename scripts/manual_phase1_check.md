# Phase 1 Manual Exit-Criterion Validation

This is the human-observed companion to the automated proof in
`tests/integration/test_phase1_exit_criterion.py` — mirroring Phase 0's
`manual_recall_check.md` dual-signoff ritual before tagging.

**Status: automated proof complete and passing; manual dogfooding pass
executed 2026-09-17 through a live Claude Code session — all 5 items
passed.** See the note at the bottom on why this is lower-stakes than
Phase 0's manual check was — though it earned its place regardless (see
Result log: it caught a real MCP server startup-latency bug the automated
suite could not have).

## Prerequisites

1. `.mcp.json` / your MCP client config must point at the *current*
   `rootmem.integration.mcp.server` (7 tools: `remember`, `recall`,
   `update`, `forget`, `search`, `related`, `ingest_session`).
2. **Restart your Claude Code (or Cursor) session** if it was already
   running before this phase's server changes landed — MCP tool lists are
   fetched once at connection time, not live-refreshed. (Confirmed
   firsthand in this session: an already-connected session still only saw
   the old 5-tool, pre-Phase-1 `search` schema.)
3. `.env` has `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY` set — both tool
   calls below make real, billed API calls.

## Checklist

- [x] **`ingest_session` — capture + extract**: ask the agent to ingest a
      transcript containing a checkable fact (e.g. "ingest this: Alice
      works at Acme Corp"). Confirm it calls `ingest_session` (not
      `remember`) and reports `relations_extracted >= 1`.

- [x] **Contradiction**: ask it to ingest a second, contradicting
      transcript ("ingest this: Alice joined Globex as an engineer").
      Confirm the tool response shows `superseded_count: 1`.

- [x] **`related`**: ask the agent what it knows about Alice's employment
      history. Confirm it calls `related` (or you ask it to explicitly) and
      the response includes both the Acme and Globex relations, with the
      Acme one showing a non-null `valid_to`.

- [x] **Semantic search**: ask a question with no lexical overlap with any
      stored fact (e.g. "who does Alice work for currently" if the exact
      word "employ" was never used). Confirm `search` is called and
      returns the right memory.

- [x] **Restart, then recall**: fully restart the client, ask it to recall
      the Alice facts again — confirms Phase 0's cross-session guarantee
      still holds with Phase 1's schema changes in place.

## Result log

**2026-09-17, live Claude Code session, namespace `manual-check-live`:**

1. `ingest_session("Alice works at Acme Corp.")` → `entities_extracted: 2`,
   `relations_extracted: 1`. First run also surfaced that the MCP server was
   failing to connect at all (client showed "Connection closed"/"Failed",
   stuck reconnecting) — root-caused live to a startup-latency bug (eager
   `VoyageEmbeddingProvider`/`AnthropicExtractionProvider` construction
   taking 27-57s, past the client's ~30s connection timeout) and fixed
   before this checklist could even begin (commit `1fcafc1`). Handshake now
   ~18.7s consistently.
2. `ingest_session("Alice joined Globex as an engineer.")` →
   `superseded_count: 1`, `contested_count: 0`. Confirmed.
3. `related(entity_name="Alice", entity_type="Person")` → both relations
   returned: Acme relation `is_active: false`, `valid_to` set,
   `superseded_by` pointing at the Globex relation id; Globex relation
   `is_active: true`, `valid_to: null`, `supersedes` pointing back. Confirmed.
4. Independent fact ingested ("The design team painted the breakroom wall a
   deep shade of teal last weekend.") — first 3 `ingest_session` calls in
   this session came back `embedded: false` (Voyage's 3-req/min free-tier
   cap, still cooling down from earlier test runs); retried after ~60s and
   got `embedded: true`. Query "what color did they use in the shared
   kitchen area" (zero lexical overlap): `search(mode="text")` → empty
   results; `search(mode="semantic")` → correctly returned the teal fact
   (score 0.478). Confirmed — the vector component does real work.
5. Restarted the Claude Code session, asked "Remind me about Alice's
   employment" → `related` correctly returned the same two relations in the
   same state (Globex active, Acme superseded) after reconnecting to the
   restarted MCP server. Confirmed.

All 5 items passed. Full findings recorded in `docs/retro/phase1-retro.md`.

---

## Why this is lower-stakes than Phase 0's manual check

Phase 0 had no automated substitute for the manual check — it was the
*only* proof the cross-session guarantee worked at all. Phase 1 is
different: `tests/integration/test_phase1_exit_criterion.py` already
proves the entire scenario (extraction, contradiction resolution, correct
bi-temporal history, semantic-vs-full-text search) end-to-end against the
real MCP protocol, real Postgres, real Voyage, and real Anthropic — nothing
about this checklist tests something the automated suite doesn't already
cover with equal or greater rigor. This checklist's value is narrower:
confirming a real agent (not a test harness driving the MCP client
directly) naturally chooses to call the right tools given a natural-language
prompt, which is a genuine, separate thing worth checking before tagging,
but not the load-bearing proof it was in Phase 0.
