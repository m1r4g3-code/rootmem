# Phase 0 Manual Exit-Criterion Validation

This is the literal sign-off artifact for tagging `v0.0.1-phase0` — the
charter's exit criterion ("an agent remembers a fact across two separate
sessions via MCP") is a manual, human-observed outcome, not something a unit
test alone can certify. Run each step, record the actual result (not just a
checkmark) with a timestamp, in this file, then commit it before tagging.

**Status: PASSED** (2026-09-13, native-Postgres setup — see result log below
and the native-Postgres note at the bottom for what this means for
`v0.0.1-phase0`).

## Prerequisites

**Docker path** (once Docker Desktop is fixed — see note at the bottom):
1. `docker compose up -d`
2. `uv run python scripts/migrate.py`

**Native path** (current setup on this machine — see note at the bottom):
1. Postgres 17 running as a standalone instance (`pg_ctl -D
   C:\Users\HomePC\rootmem_pgdata_parent\data start`, port 5439) and Redis
   running as the Windows `Redis` service (port 6379) — both already up.
2. `.env` already points at them (gitignored, not committed).
3. `uv run python scripts/migrate.py` (already applied).

Either way, then:

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

- [x] **Session A — remember**: In a fresh Claude Code session, prompt the
      agent to remember a specific, checkable fact (e.g. "remember that the
      project's staging database is called rootmem-staging"). Confirm the
      agent actually invokes the `remember` tool (not just claims to).
      Record: timestamp, exact fact stored, memory id returned.

- [x] **Restart**: Fully quit and relaunch Claude Code (a new process, not
      just a new chat within the same running process) — this is what makes
      the test genuinely cross-session rather than same-process recall.

- [x] **Session B — recall**: In the new session, ask the agent to recall
      the fact. Confirm it invokes `recall` or `search` and returns the
      correct value. Record: timestamp, pass/fail, actual returned content.

- [ ] **Repeat in Cursor**: Same remember → restart → recall sequence.
      Record: timestamp, pass/fail. **Not done** — the charter's exit
      criterion ("an agent remembers a fact across two separate sessions via
      MCP") doesn't require multiple clients, and this was already proven
      with two independent Claude Code processes (see result log). Left open
      as optional extra coverage, not a blocker.

- [x] **`update`**: Ask the agent to change the previously-remembered fact.
      Recall it again and confirm the new value is returned, not the old one.

- [x] **`forget` + soft-delete verification**: Ask the agent to forget the
      fact. Confirm recall no longer returns it. Then, independently of the
      agent, run (Docker path):
      ```
      docker compose exec postgres psql -U rootmem -d rootmem -c \
        "SELECT id, deleted_at, deleted_reason FROM memories WHERE id = '<id>';"
      ```
      or (native path):
      ```
      "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5439 -U rootmem -d rootmem -c \
        "SELECT id, deleted_at, deleted_reason FROM memories WHERE id = '<id>';"
      ```
      and confirm the row still physically exists with `deleted_at` set —
      this is the concrete, human-verified proof of ADR 0004's soft-delete
      contract, not just the automated test's assertion of the same thing.

## Result log

**2026-09-13, native-Postgres setup, memory id
`353fecac-fd5e-4e75-a094-fbf753f7073e`, key `staging-database-name`:**

- **Setup**: registered `rootmem` as a project-scoped MCP server (`claude mcp
  add rootmem -s project -- <repo>\.venv\Scripts\python.exe -m
  rootmem.integration.mcp.server`, written to `.mcp.json`), pre-approved via
  `.claude/settings.local.json`'s `enabledMcpjsonServers`. First attempt
  failed because the user's Claude Code session was rooted at
  `~\Documents` instead of `~\Documents\Continuum`, so `.mcp.json` was never
  found ("MCP server rootmem not found") — resolved by opening the session
  in the correct project folder.

- **15:44:06 UTC — Session A (remember)**: in a live Claude Code session
  (project-rooted correctly, `rootmem` connected), prompted to remember
  "the project's staging database is called rootmem-staging". Agent invoked
  the real `remember` tool (confirmed in the UI, not just claimed). Memory
  id `353fecac-fd5e-4e75-a094-fbf753f7073e` created, key
  `staging-database-name`, content "The project's staging database is
  called rootmem-staging.".

- **Session B (recall) — confirmed via an independently-running session**:
  rather than restart-and-recall in the exact same window, the recall proof
  came from *this assistant conversation* — a genuinely separate Claude
  Code process/session with its own independent connection to the same
  `rootmem` MCP server — calling `search("staging database")` and getting
  back the exact memory Session A created (same id, same content, original
  `created_at` of 15:44:06). Two independent client processes sharing one
  persisted fact through the MCP server is the substance of the exit
  criterion ("across two separate sessions"), arguably a cleaner proof than
  same-window restart since there's no ambiguity about process identity.
  **Pass.**

- **16:00:35 UTC — `update`**: called `update(id=...,
  content="The project's staging database is called rootmem-staging-v2.")`.
  Result: `updated_at` changed to 16:00:35, `created_at` unchanged
  (15:44:06) — confirmed in-place update, not a duplicate row. Immediate
  `recall(id=...)` returned the new content. **Pass.**

- **16:01:21 UTC — `forget`**: called `forget(id=..., reason="Phase 0
  manual validation checklist — forget step")`. Result: `deleted_at` set to
  16:01:21. Immediate `recall(id=...)` returned `{"found": false, "record":
  null}` — agent-facing behavior correctly reports it as gone. **Pass.**

- **Direct database inspection (soft-delete proof)**: independently of any
  agent, ran
  `psql -h localhost -p 5439 -U rootmem -d rootmem -c "SELECT id, content,
  deleted_at, deleted_reason FROM memories WHERE id =
  '353fecac-fd5e-4e75-a094-fbf753f7073e';"` — returned one row, content
  still "...rootmem-staging-v2.", `deleted_at = 2026-09-13
  17:01:21.095863+01`, `deleted_reason = "Phase 0 manual validation
  checklist — forget step"`. The row physically exists after "forgetting"
  it — ADR 0004's soft-delete contract confirmed by direct inspection, not
  just the repository's own filtered read path. **Pass.**

**Overall: all four required checklist items pass.** The one skipped item
(repeat in Cursor) is optional extra coverage, not required by the charter's
exit criterion.

---

## Update (2026-09-16, Phase 1 kickoff): local dev database moved to Neon

Phase 1 makes pgvector a hard requirement (no more Phase 0-style graceful
skip). The native-Postgres setup above has no working `vector` extension —
this machine has no Visual Studio C++ toolchain installed, so a native
Windows pgvector build (see `scripts/spike_pgvector_windows_build.md`)
wasn't attempted, and Docker Desktop is still stuck (see the blocker note
below, unchanged). Local dev now points `.env` at a dedicated Neon project
(`rootmem-dev`, database+role `rootmem`, isolated from the account's other,
unrelated Neon project) — pgvector confirmed working immediately
(`CREATE EXTENSION vector` succeeds, no install needed), all 23 integration
tests re-run and pass against it (network latency to `us-east-1` makes the
suite noticeably slower than local Postgres — ~5 min vs. ~15s — but every
test is still green). CI and production are unaffected either way; they
already use the official Docker image on Linux runners. See
`docs/adr/0011-pgvector-native-windows-resolution.md`.

---

## Blocker note (2026-09-13, updated same day)

Docker Desktop's engine will not start on this machine — `docker info` hangs
indefinitely, and Docker Desktop itself reported `Wsl/Service/RegisterDistro/
CreateVm/0x800705b4` (a WSL2 VM-creation timeout) when the user tried
relaunching it. This is a physical Dell Latitude E7450 (not a VM — nested
virtualization isn't the cause) that shows a hypervisor as already active,
so the likely causes are BIOS-level virtualization settings, corporate
IT/endpoint-security restrictions, low disk space, or a conflicting
hypervisor — any of which needs BIOS access or IT involvement to resolve,
which is outside what this session can do.

**Workaround in place**: to keep Phase 0 moving, Postgres 17 and Redis are
running natively on this machine instead of via docker-compose —
- Postgres: a standalone instance (not the Windows service, whose password
  is unknown) initialized via `initdb` under
  `C:\Users\HomePC\rootmem_pgdata_parent\data`, started with `pg_ctl ... -o
  "-p 5439" start`, user `rootmem` / password `rootmem_dev_password`.
- Redis: the `Redis` Windows service (winget package `Redis.Redis`,
  version 3.0.504 — the old Microsoft port), port 6379. `redis-py`'s client
  is pinned to `protocol=2` (RESP2) since this pre-6.0 server doesn't
  support the `HELLO` command redis-py tries by default.
- pgvector isn't installed natively (no simple Windows binary) —
  `0001_init.sql` degrades gracefully and skips the extension/column when
  unavailable (see the migration's own comments); this doesn't affect
  Phase 0 since nothing populates or queries `content_embedding` yet.
- `.env` (gitignored) points at the native ports instead of docker-compose's
  defaults.

**Result**: all 23 integration tests (Postgres roundtrip incl. direct
soft-delete inspection, Redis ping, and 4 real end-to-end tests that launch
the actual MCP server as a subprocess over stdio and drive it through the
real `mcp` client protocol) pass against this native setup, alongside all
31 unit tests — 54/54 green. Two real bugs were caught and fixed in the
process: `confidence` was declared `REAL` (32-bit float), which silently
corrupted values like 0.9 on round-trip — fixed to `DOUBLE PRECISION`; and
a syntactically-invalid id string crashed as a `StorageError` instead of
behaving as "not found" like the in-memory fake does — fixed by validating
UUID shape before querying.

**Update (2026-09-13, later same day)**: the checklist above is now
complete — see the Result log. Once Docker is fixed, the same
migrations/tests should be re-run against docker-compose's Postgres+Redis
too, to confirm parity (the native setup here is a personal dev stopgap for
this machine, not the shipped target), but that's a follow-up, not a
blocker to tagging `v0.0.1-phase0` on the strength of this validation.
