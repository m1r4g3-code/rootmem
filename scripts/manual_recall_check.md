# Phase 0 Manual Exit-Criterion Validation

This is the literal sign-off artifact for tagging `v0.0.1-phase0` — the
charter's exit criterion ("an agent remembers a fact across two separate
sessions via MCP") is a manual, human-observed outcome, not something a unit
test alone can certify. Run each step, record the actual result (not just a
checkmark) with a timestamp, in this file, then commit it before tagging.

**Status: NOT YET RUN** — blocked on local Docker Desktop, see note at the
bottom of this file.

## Prerequisites

1. `docker compose up -d`
2. `uv run python scripts/migrate.py`
3. Configure Claude Code's MCP settings (or Cursor's) to launch:
   ```
   command: <path to uv or python>
   args: ["run", "python", "-m", "rootmem.integration.mcp.server"]
   cwd: <repo root>
   ```
   (or run `uv run python -m rootmem.integration.mcp.server` directly and
   point the client at the resulting stdio process, per that client's MCP
   config format.)

## Checklist

- [ ] **Session A — remember**: In a fresh Claude Code session, prompt the
      agent to remember a specific, checkable fact (e.g. "remember that the
      project's staging database is called rootmem-staging"). Confirm the
      agent actually invokes the `remember` tool (not just claims to).
      Record: timestamp, exact fact stored, memory id returned.

- [ ] **Restart**: Fully quit and relaunch Claude Code (a new process, not
      just a new chat within the same running process) — this is what makes
      the test genuinely cross-session rather than same-process recall.

- [ ] **Session B — recall**: In the new session, ask the agent to recall
      the fact. Confirm it invokes `recall` or `search` and returns the
      correct value. Record: timestamp, pass/fail, actual returned content.

- [ ] **Repeat in Cursor**: Same remember → restart → recall sequence.
      Record: timestamp, pass/fail.

- [ ] **`update`**: Ask the agent to change the previously-remembered fact.
      Recall it again and confirm the new value is returned, not the old one.

- [ ] **`forget` + soft-delete verification**: Ask the agent to forget the
      fact. Confirm recall no longer returns it. Then, independently of the
      agent, run:
      ```
      docker compose exec postgres psql -U rootmem -d rootmem -c \
        "SELECT id, deleted_at, deleted_reason FROM memories WHERE id = '<id>';"
      ```
      and confirm the row still physically exists with `deleted_at` set —
      this is the concrete, human-verified proof of ADR 0004's soft-delete
      contract, not just the automated test's assertion of the same thing.

## Result log

_(Fill in as each step is actually run — date, exact commands/prompts used,
and actual observed output, not just pass/fail.)_

---

## Blocker note (2026-09-13)

Docker Desktop's engine will not start on this machine — `docker info`
fails with `failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine`, and `wsl --status` reports
"Windows Subsystem for Linux has no installed distributions," which means
Docker Desktop's WSL2 backend distros (`docker-desktop`,
`docker-desktop-data`) were never registered. Fixing this requires an
elevated (Administrator) session to verify/enable the WSL2 and Virtual
Machine Platform Windows features and likely a restart — outside what an
unprivileged shell can do. This checklist cannot be executed, and
`v0.0.1-phase0` cannot be tagged, until that's resolved.
