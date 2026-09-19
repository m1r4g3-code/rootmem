# Phase 5 Research Memo — Remote Transport, Agent Identity & Test Isolation

**Date:** 2026-09-19. Inputs: phase 0-4 retros and requirements, ADR 0002, installed `mcp` 2.2.0.

## What earlier phases left for Phase 5

- Cross-instance identity continuity and remote transport, named "frontier / Phase 4/5+" in every requirements doc but never defined.
- ADR 0002 places HTTP/SSE in "Phase 6 (Ecosystem Integration)"; later requirements say "Phase 5+". This phase takes it, by the user's decision.
- Phase 4's retro: integration suites `TRUNCATE` the live database; a separate test database was recommended.

## Repo findings (verified by reading code)

- The server is stdio only (`run_stdio_async`). Every tool is a closure in `build_server` and takes a client-supplied `namespace`; `update`/`forget` take only an id.
- Nothing is per-caller: `source` is free text, `settings.audit_actor` is one constant.
- The installed SDK (`mcp` 2.2.0) provides `run_streamable_http_async`, `streamable_http_app()` (Starlette), `custom_route`, and bearer auth (`token_verifier`, `AuthSettings`, `AuthContextMiddleware`). Starlette and uvicorn arrive transitively but are not declared.
- No separate test database exists; four integration fixtures `TRUNCATE` tables.

## Definition adopted: identity continuity

The same agent identity, presented from any client instance or machine, sees the same memory (its owned namespaces), and every write is attributed to that identity in the audit chain, across client and server restarts. Continuity comes from a durable server-side identity record, not from client state.

## Design consequences

- Identity is a database row referenced by a bearer token stored only as a SHA-256 digest (ADR 0027).
- Streamable HTTP, stateless, mandatory auth (ADR 0028): stateless keeps any client instance interchangeable.
- Authorization is namespace ownership checked in one helper before any repository call (ADR 0029).
- Audit actor becomes the identity name (ADR 0030).
- Tests get their own database and a guard against truncating anything else (ADR 0031).

## Open questions carried out

- TLS, rate limiting and token rotation are deliberately left to deployment or a later phase.
- Memory export/import between deployments was declined for this phase.
