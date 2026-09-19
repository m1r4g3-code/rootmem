# Phase 5 Retrospective — Remote Transport, Agent Identity & Test Isolation

**Status:** Filled in after `v0.5.0-phase5`'s automated exit-criterion test (1 passed, 56.88s), 261 unit tests, the Postgres integration suites (83 + 6 identity tests) against a separate test database, the Phase 1-4 exit tests re-run, and a live manual pass (7/7) with a real Claude Code client over HTTP on 2026-09-19.

## What shipped

- **Remote transport (ADR 0028):** stateless streamable HTTP behind bearer auth, selected by `ROOTMEM_TRANSPORT=http` (stdio stays the default). It refuses to start without the token verifier and binds loopback unless explicitly allowed.
- **Agent identity (ADR 0027):** an `identities` table (migration 0009), tokens stored only as SHA-256 digests, an `IdentityRepository` Protocol (fake + Postgres, one contract suite), and a CLI to create, list and revoke.
- **Authorization (ADR 0029):** one `guarded` wrapper runs before every tool body, so a denied call has no side effects and writes no audit entry. `update`/`forget` take only an id, so a new `namespace_of` check runs first; a foreign memory answers exactly like a missing one. With auth required and no identity present, calls fail closed.
- **Attribution (ADR 0030):** the audit actor is the authenticated identity name, inside the hashed row.
- **Test isolation (ADR 0031):** tests run on `<db>_test`, a guard refuses `TRUNCATE` on any other database, and `scripts/create_test_db.py` creates and migrates it. This is what Phase 4's retro asked for.
- 13 tools unchanged in count; migration 0009; `mcp>=2.2` pinned, `starlette`/`uvicorn` declared.

## What worked

- **The SDK did most of the transport work.** `mcp` 2.2.0 already ships streamable HTTP and bearer middleware, so the change was a verifier, a transport switch and a guard wrapper, not a web server.
- **One guard, not thirteen edits.** A decorator reading the `namespace` argument by signature covered every tool, and a unit test asserts the tool schemas survive it.
- **Real client, real denial.** In the live pass the client was refused on the default namespace and, unprompted, did not try to get around it.
- **Test isolation paid off immediately.** After the change, 83 integration tests ran and the live database's 3 memories were untouched.

## What didn't work / surprises

- **A stale test hid for two phases.** `test_lists_all_nine_tools` had been wrong since Phase 3 added tools; I only ran part of the integration directory in Phases 3 and 4. Now fixed (13 tools). Lesson: run the whole integration directory before tagging, not just the files I touched.
- **Back-to-back external tests trip Voyage's rate limit.** The Phase 2 exit test failed after the Phase 1 test used up the 3 requests/minute allowance (embeddings degraded, so nothing clustered); it passes alone (122s). Environmental, but it means the exit tests should not be chained in one run.
- **A mistyped path created a stray file** at `C:\AppData` while patching; I removed the file and the empty folder. Nothing else was written outside the project.
- **The manual checklist needed the user's real client.** My own session cannot load the remote server entry, so the read/write/continuity steps ran through the user's client; I ran the server restart, audit-actor check and revocation myself.

## Limits worth stating

- No TLS: the HTTP server is plain HTTP on loopback by default; a non-loopback deployment needs a reverse proxy in front.
- Tokens are bearer secrets with no expiry or rotation; revocation is immediate but a leaked, unrevoked token is fully valid. The token used in the live check was revoked afterwards.
- Authorization is namespace ownership only; there are no read-only or per-tool scopes.
- The lockfile `uv.lock` was not regenerated locally (no `uv` on this machine); CI runs `uv sync`, which re-resolves. `mcp` 2.2.0 was already locked.
- Identity continuity here means "same token, same namespaces, same attribution"; there is no memory export/import between deployments.

## Decisions to revisit in Phase 6

- Token expiry and rotation; per-tool or read-only scopes.
- TLS and rate limiting in front of the HTTP server.
- A REST facade and memory export/import, both declined for this phase.
- Calibration of ranking weights and decay once real usage exists; carried unchanged: session-trace batch scoping, 0.80 thresholds, first-episode auto-trigger.

## Metrics captured

- HTTP exit-criterion test: 56.88s. Unit tests: 261 in ~11s. Integration (test database): 83 passed in 636s, plus 6 identity tests.
- Phase 1-3 exit tests re-run: Phase 1 and 3 passed; Phase 2 passed alone (122s) after a rate-limit failure when chained.
- `mypy --strict`: 160 files clean.
