# Phase 1 Manual Exit-Criterion Validation

This is the human-observed companion to the automated proof in
`tests/integration/test_phase1_exit_criterion.py` — mirroring Phase 0's
`manual_recall_check.md` dual-signoff ritual before tagging.

**Status: automated proof complete and passing; manual dogfooding pass not
yet run.** See the note at the bottom on why this is lower-stakes than
Phase 0's manual check was.

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

- [ ] **`ingest_session` — capture + extract**: ask the agent to ingest a
      transcript containing a checkable fact (e.g. "ingest this: Alice
      works at Acme Corp"). Confirm it calls `ingest_session` (not
      `remember`) and reports `relations_extracted >= 1`.

- [ ] **Contradiction**: ask it to ingest a second, contradicting
      transcript ("ingest this: Alice joined Globex as an engineer").
      Confirm the tool response shows `superseded_count: 1`.

- [ ] **`related`**: ask the agent what it knows about Alice's employment
      history. Confirm it calls `related` (or you ask it to explicitly) and
      the response includes both the Acme and Globex relations, with the
      Acme one showing a non-null `valid_to`.

- [ ] **Semantic search**: ask a question with no lexical overlap with any
      stored fact (e.g. "who does Alice work for currently" if the exact
      word "employ" was never used). Confirm `search` is called and
      returns the right memory.

- [ ] **Restart, then recall**: fully restart the client, ask it to recall
      the Alice facts again — confirms Phase 0's cross-session guarantee
      still holds with Phase 1's schema changes in place.

## Result log

_(Fill in as each step is actually run — date, exact prompts, actual
observed output.)_

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
