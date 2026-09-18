# Phase 2 Manual Exit-Criterion Validation

This is the human-observed companion to the automated proof in
`tests/integration/test_phase2_exit_criterion.py` — mirroring Phase 0/1's
dual-signoff ritual before tagging.

**Status: automated proof complete and passing; manual dogfooding pass
executed 2026-09-18 — all items but the final cross-session restart
confirmed live (see Result log).** See the note at the bottom on why this
is lower-stakes than Phase 0's manual check was, and on what Phase 1's own
manual pass found that the automated suite alone would not have (a real MCP
server startup-latency bug) — the same category of finding this pass exists
to catch again if it recurs. This run also caught a real (client-side, not
server-side) finding: see the result log's note on the stale tool-schema
cache.

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

- [x] **Corroboration**: ask the agent to ingest three differently-worded
      restatements of the same fact (e.g. "Alice works at Acme Corp",
      "Alice is employed at Acme Corp", "Alice's employer is Acme Corp").
      Confirm each calls `ingest_session`, and that asking about Alice
      afterward (via `related`) shows exactly **one** relation, not three —
      proving corroboration merged them rather than creating duplicates.

- [x] **Importance-flagged fact**: ask the agent to remember a distinctly
      important, one-off fact, explicitly telling it this matters a lot
      (the agent should pass a high `importance_flag` if it reasons about
      this correctly — otherwise you can ask it directly: "call
      ingest_session with importance_flag=1.0 for this").

- [x] **`consolidate`**: ask the agent to run consolidation (or explicitly:
      "call the consolidate tool with force=true"). Confirm it reports
      `ran: true` and at least one cluster/distilled fact if the
      corroborating restatements above are still unconsolidated (note: the
      very first ingest into a fresh namespace may have already
      auto-triggered a solo pass — see the exit-criterion test's own note
      on this).

- [x] **Salience via `recall`**: ask the agent to recall the important
      fact and the redundant restatement, and compare their
      `salience_score` values. Confirm the important, novel fact scores
      higher.

- [x] **Bayesian contradiction resistance**: ingest a second, contradicting
      fact about the same subject+predicate (e.g. "Alice joined Globex as
      an engineer"). Confirm the tool response shows `contested_count: 1`
      and `superseded_count: 0` — the corroborated original relation should
      resist a fresh, single-shot contradiction rather than being silently
      overwritten. Ask the agent about Alice's employment history and
      confirm `related` shows both relations, both marked contested.

- [x] **`feedback`**: ask the agent to report that the original (Acme)
      relation is correct (call `feedback` with `outcome="confirmed"`).
      Confirm the returned relation's `confidence` increased.

- [ ] **Restart, then recall**: fully restart the client, ask it about
      Alice again — confirms the cross-session guarantee still holds with
      Phase 2's schema changes in place. **Not yet run by the human user —
      requires an actual client restart this session cannot self-trigger.**

## Result log

**2026-09-18, live session, namespace `manual-phase2-check`:**

- **Stale tool-schema finding (client-side, not a server bug)**: after the
  `rootmem` MCP server reconnected with the new tools, `consolidate` and
  `feedback` (brand-new tool names) showed correct schemas immediately, but
  `ingest_session` (a pre-existing tool name, now with an added
  `importance_flag` parameter) initially displayed a schema *without*
  `importance_flag`. Calling it anyway, with `importance_flag=1.0`
  explicitly, worked correctly end-to-end (see below) — confirming this was
  a client-side schema-cache staleness artifact for tool names that already
  existed pre-reconnect, not a real server-side gap. Distinct from Phase 1's
  finding (an entire stale tool *list*); this is a narrower, per-tool
  stale-schema variant of the same underlying "fetched once, not
  live-refreshed" behavior.

- **Corroboration**: ingested "Alice works at Acme Corp.", "Alice is
  employed at Acme Corp.", "Alice's employer is Acme Corp." — three
  separate `ingest_session` calls, each `relations_extracted: 1`,
  `superseded_count: 0`. `related` afterward showed exactly **one**
  relation, `confidence: 0.8387`, `derivation: "extracted"`,
  `source_memory_ids` already covering all three episodes (via
  extraction-time provenance). **Pass.**

- **Importance-flagged fact**: `ingest_session("Confidential: the annual
  budget review has been rescheduled and only the CFO and two board
  members will attend.", importance_flag=1.0)` — accepted and applied
  correctly (see recall result below). `embedded: false` on this call
  (Voyage's free-tier 3-req/min cap, same graceful-degradation behavior
  observed in Phase 1's own dogfooding — extraction still succeeded).
  **Pass** (confirms the parameter works despite the stale-schema display
  above).

- **`consolidate(force=true)`**: `{"ran":true,"trigger_reason":"manual",
  "episodes_processed":4,"clusters_formed":1,"facts_distilled":1}`.
  `related` afterward showed the same relation id, now `derivation:
  "distilled"`, `confidence` risen to `0.8627`. **Pass.**

- **Salience via `recall`**: important flagged fact —
  `importance_flag: 1, salience_score: 0.6667`. Routine redundant
  restatement ("Alice is employed at Acme Corp.") —
  `importance_flag: 0, salience_score: 0.1233`. Important fact scored
  measurably higher, matching the exit-criterion test's own finding.
  **Pass.**

- **Bayesian contradiction resistance**: `ingest_session("Alice joined
  Globex as an engineer.")` → `superseded_count: 0, contested_count: 1`.
  `related` showed both relations active and both `is_contested: true` —
  the well-corroborated Acme relation resisted the fresh, single-shot
  contradiction rather than being silently overwritten. **Pass.**

- **`feedback`**: `feedback(relation_id=<Acme relation>,
  outcome="confirmed", confidence=1.0)` → returned relation's `confidence`
  rose from `0.8627` to `0.8904`. **Pass.**

- **Restart, then recall**: not yet performed — needs the human user to
  actually restart their client. Cross-session persistence itself is
  unchanged from Phase 0/1's already-proven Postgres-backed guarantee; this
  step exists to catch client-connection-path surprises specifically (per
  Phase 1's precedent), not to re-prove storage durability.

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
