# Phase 5 Requirements & Constraints — Remote Transport, Agent Identity & Test Isolation

## Exit criterion

> Against a real uvicorn server process in HTTP mode and real Postgres:
> **(a)** a call with no token, an unknown token, or a revoked token is rejected (HTTP 401);
> **(b)** identity A (owns `ns-a`) writes in `ns-a` from client 1; a brand-new client 2 with the same token recalls and searches it, including after a server restart;
> **(c)** identity B cannot `recall`, `search`, `remember`, `update`, `forget` or `verify_audit` in `ns-a`: an authorization error, and nothing changes;
> **(d)** the audit chain for `ns-a` names identity A as actor and `verify_audit` is valid;
> **(e)** stdio mode is unchanged (all Phase 0-4 tests pass untouched);
> **(f)** the integration suites, run with default config, cannot modify the main database.

Gate for tagging `v0.5.0-phase5`: one automated test plus a live manual pass (`scripts/manual_phase5_check.md`).

## Functional requirements

- FR1: `identities` table and `IdentityRepository` Protocol (create, get by token digest, list, revoke), Postgres and in-memory, one contract suite.
- FR2: tokens are 256-bit random, returned once at creation, stored only as SHA-256; comparison is by digest lookup.
- FR3: CLI `python -m rootmem.identity.cli create|list|revoke`.
- FR4: `ROOTMEM_TRANSPORT=stdio|http` (default stdio); http mode serves streamable HTTP, stateless, and refuses to start without the token verifier.
- FR5: pure `authorize_namespace(identity, namespace)`; one `resolve_caller` helper used by every tool; stdio resolves to a fixed local identity owning all namespaces.
- FR6: `MemoryRepository.namespace_of(memory_id)` so `update`/`forget` are authorized before mutating.
- FR7: audit actor is the authenticated identity name.
- FR8: integration tests use a separate database; a guard refuses `TRUNCATE` unless the connected database name ends in `_test`; `scripts/create_test_db.py` creates it and migrates it.

## Non-functional requirements

- NFR1: stdio startup and behavior unchanged (handshake budget from Phase 3/4 retros).
- NFR2: `mypy --strict`, zero suppressions; authorization logic pure and unit-tested.
- NFR3: plaintext tokens are never stored or logged.
- NFR4: http mode binds loopback by default; a non-loopback bind is an explicit setting.
- NFR5: a denied call must have no side effects, including no audit-log write under the denied namespace.
- NFR6: `mcp>=2.2`; `starlette` and `uvicorn` declared.

## Non-goals

REST facade; memory export/import; OAuth flows, user login, token refresh or rotation; TLS termination; rate limiting; per-tool scopes beyond namespace ownership; multi-node deployment; learned ranking.
