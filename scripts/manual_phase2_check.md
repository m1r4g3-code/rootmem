# Phase 2 Manual Exit-Criterion Validation

This is the human-observed companion to the automated proof in
`tests/integration/test_phase2_exit_criterion.py` — mirroring Phase 0/1's
dual-signoff ritual before tagging.

**Status: automated proof complete and passing; manual dogfooding pass not
yet run.** See the note at the bottom on why this is lower-stakes than
Phase 0's manual check was, and on what Phase 1's own manual pass found
that the automated suite alone would not have (a real MCP server
startup-latency bug) — the same category of finding this pass exists to
catch again if it recurs.

## Prerequisites

1. `.mcp.json` / your MCP client config must point at the *current*
   `rootmem.integration.mcp.server` (9 tools: `remember`, `recall`,
   `update`, `forget`, `search`, `related`, `ingest_session`, `consolidate`,
   `feedback`).
2. **Restart your Claude Code (or Cursor) session** if it was already
   running before this phase's server changes landed — MCP tool lists are
   fetched once at connection time, not live-refreshed (confirmed the hard
   way during Phase 1's own manual check).
3. `.env` has `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY` set — `ingest_session`
   and `consolidate` both make real, billed API calls.

## Checklist

- [ ] **Corroboration**: ask the agent to ingest three differently-worded
      restatements of the same fact (e.g. "Alice works at Acme Corp",
      "Alice is employed at Acme Corp", "Alice's employer is Acme Corp").
      Confirm each calls `ingest_session`, and that asking about Alice
      afterward (via `related`) shows exactly **one** relation, not three —
      proving corroboration merged them rather than creating duplicates.

- [ ] **Importance-flagged fact**: ask the agent to remember a distinctly
      important, one-off fact, explicitly telling it this matters a lot
      (the agent should pass a high `importance_flag` if it reasons about
      this correctly — otherwise you can ask it directly: "call
      ingest_session with importance_flag=1.0 for this").

- [ ] **`consolidate`**: ask the agent to run consolidation (or explicitly:
      "call the consolidate tool with force=true"). Confirm it reports
      `ran: true` and at least one cluster/distilled fact if the
      corroborating restatements above are still unconsolidated (note: the
      very first ingest into a fresh namespace may have already
      auto-triggered a solo pass — see the exit-criterion test's own note
      on this).

- [ ] **Salience via `recall`**: ask the agent to recall the important
      fact and the redundant restatement, and compare their
      `salience_score` values. Confirm the important, novel fact scores
      higher.

- [ ] **Bayesian contradiction resistance**: ingest a second, contradicting
      fact about the same subject+predicate (e.g. "Alice joined Globex as
      an engineer"). Confirm the tool response shows `contested_count: 1`
      and `superseded_count: 0` — the corroborated original relation should
      resist a fresh, single-shot contradiction rather than being silently
      overwritten. Ask the agent about Alice's employment history and
      confirm `related` shows both relations, both marked contested.

- [ ] **`feedback`**: ask the agent to report that the original (Acme)
      relation is correct (call `feedback` with `outcome="confirmed"`).
      Confirm the returned relation's `confidence` increased.

- [ ] **Restart, then recall**: fully restart the client, ask it about
      Alice again — confirms the cross-session guarantee still holds with
      Phase 2's schema changes in place.

## Result log

_(Fill in as each step is actually run — date, exact prompts, actual
observed output.)_

---

## Why this is lower-stakes than Phase 0's manual check, but not zero-stakes

Phase 0 had no automated substitute for the manual check — it was the
*only* proof the cross-session guarantee worked at all. Phase 2, like
Phase 1, has a real automated end-to-end proof
(`tests/integration/test_phase2_exit_criterion.py`) covering corroboration,
distillation, salience, Bayesian contradiction resistance, and feedback
against the real MCP protocol, real Postgres, real Voyage, and real
Anthropic. This checklist's distinct value, proven real by Phase 1's own
experience: a real client (not a test harness driving the MCP client
directly) exercises the *actual* connection/startup path and lets a real
agent choose which tools to call from natural language — Phase 1's manual
pass caught a genuine MCP server startup-latency bug the automated suite's
Python-driven harness never would have, precisely because the harness has
no realistic client-side connection timeout to violate. This pass exists to
catch that same category of surprise again, not to re-prove logic the exit
criterion test already covers with equal rigor.
