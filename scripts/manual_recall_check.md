# Phase 0 Manual Exit-Criterion Validation

This is the literal sign-off artifact for tagging `v0.0.1-phase0` — the
charter's exit criterion ("an agent remembers a fact across two separate
sessions via MCP") is a manual, human-observed outcome, not something a unit
test alone can certify. Run each step, record the actual result (not just a
checkmark) with a timestamp, in this file, then commit it before tagging.

**Status: NOT YET RUN** (this checklist specifically — see the native-Postgres
note below for what *has* been verified automatically).

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

_(Fill in as each step is actually run — date, exact commands/prompts used,
and actual observed output, not just pass/fail.)_

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

**What's still genuinely unverified**: this checklist's actual point — a
real Claude Code or Cursor session remembering a fact and recalling it
after a full restart. That needs a live agent session, not something
automatable from here. Once Docker is fixed, the same migration/tests
should be re-run against docker-compose's Postgres+Redis too, to confirm
parity before tagging `v0.0.1-phase0` (the native setup is a personal dev
stopgap, not the shipped target).
