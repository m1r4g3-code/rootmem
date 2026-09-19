# Phase 6 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase6_exit_criterion.py`:
a real client and real terminal, rather than scripted ones.

**Status: PASSED (10/10).** Automated proof: `tests/integration/test_phase6_exit_criterion.py` (1 passed, 224-249s); live pass complete.

## Prerequisites

1. Migrations through `0010_identity_expiry_scope.sql` applied to the main database.
2. Start the HTTP server: `ROOTMEM_TRANSPORT=http python -m rootmem.integration.mcp.server` (127.0.0.1:8765).
3. Issue identities (tokens print once):
   - `python -m rootmem.identity.cli create --name p6-writer --namespace manual-phase6 --expires-in-days 30`
   - `python -m rootmem.identity.cli create --name p6-reader --namespace manual-phase6 --scope read`
4. Add the writer to the real client, then `/mcp` reconnect (a session restart alone does not respawn servers):
   `claude mcp add --transport http rootmem-p6 http://127.0.0.1:8765/mcp --header "Authorization: Bearer <writer token>"`.

## Checklist

- [x] **Health**: `curl http://127.0.0.1:8765/healthz` returns `{"status":"ok"}` with no token.
- [x] **Real client write and read** through the writer identity in `manual-phase6`.
- [x] **REST facade**: `curl -H "Authorization: Bearer <writer>" http://127.0.0.1:8765/v1/tools` lists 13 tools; a `search` call returns the same memory the client saw.
- [x] **Read scope**: with the reader token, `search` succeeds; `remember` over REST returns 403 (and the real client, if pointed at the reader, is refused).
- [x] **Rate limit**: hammer `search` with a loop of `curl` calls under a small `RATE_LIMIT_BURST`; some return 429.
- [x] **Rotation**: `python -m rootmem.identity.cli rotate --name p6-writer`; the next call with the old token is 401, the new token works and sees the same memory.
- [x] **Export/import**: `python -m rootmem.portability.cli export --namespace manual-phase6 --out p6.jsonl`, then import into an empty namespace; `verify_audit` on the target is valid and lists an `import` entry.
- [x] **Claude Code hook**: feed the hook a real transcript path and confirm a memory appears (`echo '{"transcript_path":"<path>"}' | python -m rootmem.integrations.claude_code_hook` with `ROOTMEM_URL`/`ROOTMEM_TOKEN` set).
- [x] **Retrieval evaluation**: `python -m rootmem.evaluation.run` prints its report; read the "Read this first" limits.
- [x] **stdio still works**: the original stdio `rootmem` server still answers `search`.

## Result log

**2026-09-19, real Claude Code client over HTTP, identities `p6-writer` (readwrite, 30-day expiry) and `p6-reader` (read), namespace `manual-phase6`; server run with `RATE_LIMIT_PER_MINUTE=6 RATE_LIMIT_BURST=8`:**

- **Health:** `/healthz` returned `{"status":"ok"}` with no token; `/v1/tools` with no token returned 401. Pass.
- **Real client write/read:** the user's client wrote a memory and found it (score 0.50, breakdown shown). Pass.
- **REST facade:** `/v1/tools` listed 13 tools; a foreign namespace returned 403. Pass.
- **Read scope, real client:** through the `rootmem-p6-reader` MCP entry, `search` returned the memory and `remember` was refused: `scope 'read' does not permit 'remember'`. `verify_audit` stayed valid with 1 entry (the refusal wrote nothing). Pass.
- **Rate limit:** 14 rapid REST searches gave 200 x9, then 429 x4, then a 200 once tokens refilled. Pass.
- **Rotation:** old token 200 -> 401 immediately after `rotate`; the new token 200. Pass.
- **Export/import:** exported 1 record, imported into empty `manual-phase6-copy` (readable by its own identity, audit chain valid); a second import into the same namespace was refused. Pass. (The graph and skills round trip is covered by the automated test; this namespace held one memory.)
- **Hook:** fed a small synthetic transcript (not this session's real one, which contains tokens); the memory was created through REST with source `p6-hook`, and the tool-call payload in the transcript was not captured. Pass. A first attempt failed cleanly because I gave the hook a Git-Bash `/tmp` path Windows Python could not see; it reported the error and exited 1 without raising.
- **Evaluation:** report printed; overall nDCG@5 0.635 lexical, 0.882 semantic, 0.975 multi-factor on the small synthetic set (see the report's limits).
- **stdio:** the original stdio `rootmem` server still connects.
- **Findings during the pass:**
  - A revoked token in a client shows up as an OAuth registration failure (`Dynamic Client Registration rejected (HTTP 404)`) with an Authenticate button, not "token revoked": the client answers 401 by trying an OAuth login the server does not offer. Documented in `docs/operations.md`.
  - `claude mcp add` defaults to local scope (per project folder), which is why the first attempt showed nothing in a different project; `--scope user` fixed it.
- **Cleanup:** all five identities revoked; HTTP server stopped. The `rootmem-p6` and `rootmem-p6-reader` entries remain in the user's `~/.claude.json` (their tokens are now revoked).
