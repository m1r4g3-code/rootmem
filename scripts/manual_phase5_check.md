# Phase 5 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase5_exit_criterion.py`
(1 passed, 56.88s): a real client over real HTTP, as opposed to a scripted one.

**Status: PASSED (7/7).** Automated proof passing; live pass complete.

## Prerequisites

1. Migration `0009_identities.sql` applied (`python scripts/migrate.py`).
2. Issue an identity: `python -m rootmem.identity.cli create --name manual-agent --namespace manual-phase5` (the token is printed once).
3. Start the server in HTTP mode: `ROOTMEM_TRANSPORT=http python -m rootmem.integration.mcp.server` (binds 127.0.0.1:8765).
4. Add it to the client as a remote server with the bearer header, e.g. `claude mcp add --transport http rootmem-remote http://127.0.0.1:8765/mcp --header "Authorization: Bearer <token>"`, then `/mcp` reconnect.
5. Note: reconnect with `/mcp` (restarting the session alone did not respawn servers in Phase 4).

## Checklist

- [x] **Unauthenticated is rejected**: `curl -X POST http://127.0.0.1:8765/mcp` returns 401.
- [x] **Remote write**: from the real client, `remember` a fact in namespace `manual-phase5` through `rootmem-remote`.
- [x] **Continuity**: stop and restart the HTTP server process; reconnect the client; `recall`/`search` returns the same fact.
- [x] **Namespace denial**: the same client asking for a namespace it does not own (e.g. `default`) gets an authorization error and nothing is written.
- [x] **Audit attribution**: `verify_audit` on `manual-phase5` is valid and (checked in `psql`) the actor is `manual-agent`.
- [x] **Revocation**: `python -m rootmem.identity.cli revoke --name manual-agent`; the very next call from the client is rejected.
- [x] **stdio still works**: the original stdio `rootmem` server still answers `search` after the pass.

## Result log

**2026-09-19, real Claude Code client over HTTP (`rootmem-remote`), identity `manual-agent` owning `manual-phase5`:**

- **Unauthenticated:** `curl -X POST /mcp` with no token returned 401. Pass.
- **Namespace denial (real client, unprompted):** asked to "search Alice" in the default namespace, the client got `identity 'manual-agent' may not access this namespace`, and did not try to work around it. Pass.
- **Remote write:** `remember` and `search` in `manual-phase5` succeeded (score 0.48). Pass.
- **Continuity across a server restart:** the HTTP server process was killed and restarted; after reconnecting, `search` returned the same memory (`e05afa83...`). Pass.
- **Audit:** `verify_audit` valid, 1 entry; the entry's actor in Postgres is `manual-agent`. Pass.
- **Revocation:** a raw call with the token returned 200, then after `identity.cli revoke` returned 401 on the very next call. Pass.
- **stdio unchanged:** the original stdio `rootmem` server still answered `search`. Pass.
- **Cleanup:** identity revoked and the HTTP server stopped. The `rootmem-remote` entry remains in the client config; remove with `claude mcp remove rootmem-remote`.
