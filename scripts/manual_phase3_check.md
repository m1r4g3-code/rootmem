# Phase 3 Manual Exit-Criterion Validation

This is the human-observed companion to the automated proof in
`tests/integration/test_phase3_exit_criterion.py` — mirroring Phase 0/1/2's
dual-signoff ritual before tagging.

**Status: PASSED (7/7).** Automated proof complete and passing
(`tests/integration/test_phase3_exit_criterion.py`, 1 passed in 428.75s).
Manual dogfooding pass executed live 2026-09-18/19.

## Prerequisites

1. `.mcp.json` / your MCP client config must point at the *current*
   `rootmem.integration.mcp.server` (11 tools: `remember`, `recall`,
   `update`, `forget`, `search`, `related`, `ingest_session`, `consolidate`,
   `feedback`, `find_skill`, `get_skill`).
2. **Restart your Claude Code (or Cursor) session** if it was already
   running before this phase's server changes landed — MCP tool lists are
   fetched once at connection time, not live-refreshed (confirmed the hard
   way during Phase 1's own manual check, and again as a narrower per-tool
   variant during Phase 2's).
3. `.env` has `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY` set — `ingest_session`
   and `consolidate` both make real, billed API calls (now including a
   procedural-distillation Anthropic call per qualifying skill/lesson).
4. Migrations `0005_procedural_memory.sql` and
   `0006_procedural_memories_deferrable_supersede_fk.sql` must be applied
   (`uv run python scripts/migrate.py`).

## Checklist

- [x] **Two successful sessions, same procedure**: ask the agent to
      `ingest_session` two short, differently-worded 2-3 step accounts of
      the same successful fix (e.g. "a test failed with a KeyError from a
      missing config default; adding the default fixed it, tests pass" told
      two different ways), each with a distinct `session_id` and
      `session_outcome="success"`.

- [x] **One failed session**: ask the agent to `ingest_session` a distinct,
      related-looking but different failed attempt (e.g. "a test failed
      with a TypeError; changing an input type didn't fix it, the real
      cause was a serialization bug"), with a fresh `session_id` and
      `session_outcome="failure"`.

- [x] **`consolidate`**: ask the agent to run consolidation (or explicitly:
      "call the consolidate tool with force=true"). Confirm the response
      shows `procedures_distilled: 1` and `lessons_distilled: 1` (note: as
      with Phase 2's own manual check, the very first `ingest_session` call
      into a fresh namespace may have already auto-triggered a solo pass —
      see the exit-criterion test's own note on this; if so, run one more
      `ingest_session` before `consolidate` to ensure the sessions above are
      still unconsolidated).

- [x] **`find_skill`**: ask the agent to find a skill for a *fresh* instance
      of the same problem, described in your own words, without naming the
      skill. Confirm it returns the distilled skill ranked first (not the
      lesson).

- [x] **`get_skill`**: ask the agent to fetch the skill `find_skill`
      returned. Confirm the response is literal SKILL.md-conformant
      markdown — YAML frontmatter (`name`, `description`) followed by a
      body — and that it accurately describes the procedure.

- [x] **Apply it**: ask the agent to follow the retrieved skill's steps for
      a new (simulated) instance of the problem, and confirm it calls
      `ingest_session` reporting the outcome — a successful, ordinary
      subsequent MCP tool call, not a benchmark run (per ADR 0021's
      confirmed scoped-down exit criterion).

- [x] **Restart, then find/get again**: fully restart the client, ask it to
      find and retrieve the same skill again — confirms the cross-session
      guarantee still holds with Phase 3's schema in place.

## Result log

**2026-09-18, live session, namespace `manual-phase3-check`:**

- **Startup finding (not a logic bug)**: the first client restart after the
  Phase 3 changes timed out connecting (`CONNECT_TIMEOUT`, 30s). A direct
  handshake measurement afterward took 12.3s with all 11 tools listed --
  a cold-cache first start, not a regression; a `/mcp` reconnect succeeded.
  Worth watching: three lazy Anthropic/Voyage providers plus the `mcp`
  import (~9s cold on its own) leave less headroom under the 30s client
  timeout than before.
- **Two successful sessions** (`manual-a`, `manual-b`, 2 steps each,
  differently worded, `session_outcome="success"`) and **one failed
  session** (`manual-c`, 2 steps, `session_outcome="failure"`): all
  ingested. Under Voyage's rate limit one call degraded to
  `extraction_degraded: true` and one to `embedded: false` -- the graceful
  degradation working as designed; episodes were still stored. **Pass.**
- **`consolidate(force=true)`**: `{"ran":true,"trigger_reason":"manual",
  "episodes_processed":6,"clusters_formed":1,"facts_distilled":1,
  "procedures_distilled":1,"lessons_distilled":1}` -- all three
  distillation types in one pass. A throwaway kickoff episode absorbed the
  inline auto-trigger first, so no session trace was split. **Pass.**
- **`find_skill`** with own wording ("my tests crash with a KeyError because
  a setting has no default value configured"): returned
  `add-missing-config-default` (kind skill, score 0.402); the unrelated
  lesson did not surface. The lesson query returned
  `avoid-changing-wrong-layer` (kind lesson, score 0.366). **Pass.**
- **`get_skill("add-missing-config-default")`**: literal SKILL.md --
  `---` frontmatter with `name` and `description` (stating what and when),
  then a generalized 4-step numbered body. **Pass.**
- **Apply it**: `ingest_session` describing following the skill for a new
  KeyError succeeded (`extraction_degraded: false`). **Pass.**
- **Restart, then find/get again**: After a full client restart and MCP reconnect (2026-09-19), `find_skill` with the same own-words query returned `add-missing-config-default` (skill, score 0.402, identical to pre-restart) and `get_skill` returned the identical SKILL.md. Skill persisted across sessions. **Pass.**

---

## Why this is lower-stakes than Phase 0's manual check, but not zero-stakes

Phase 3, like Phase 1/2, has a real automated end-to-end proof
(`tests/integration/test_phase3_exit_criterion.py`) covering session-trace
grouping, procedural/lesson distillation, coexistence with episodic->
semantic distillation, semantic skill retrieval, and SKILL.md-conformant
rendering against the real MCP protocol, real Postgres, real Voyage, and
real Anthropic. This checklist's distinct value, proven real by Phase 1's
own experience and Phase 2's own client-side schema-staleness finding: a
real client exercises the actual connection/startup path and lets a real
agent choose which tools to call and how to phrase a natural-language
`find_skill` query from its own judgment, not a fixed test string — the
kind of surprise a Python-driven test harness structurally cannot produce.
