# ADR 0028: Remote transport is stateless streamable HTTP with mandatory auth

**Status:** Accepted (supersedes the transport timing in ADR 0002, which placed HTTP in Phase 6)
**Date:** 2026-09-19

## Context

ADR 0002 chose stdio and deferred HTTP, noting a remote transport adds a web server, port management and an auth surface without touching tool logic. The installed SDK (`mcp` 2.2.0) ships streamable HTTP and bearer-auth middleware.

## Decision

Add `ROOTMEM_TRANSPORT=stdio|http` (default stdio, unchanged). HTTP mode serves streamable HTTP in stateless mode, so any client instance is interchangeable, behind the SDK's bearer middleware with a `RootmemTokenVerifier`. It refuses to start without the verifier and binds loopback by default. TLS is left to a reverse proxy. Tighten to `mcp>=2.2` and declare `starlette`/`uvicorn`.

## Alternatives considered

- SSE: legacy transport, not chosen.
- A custom REST facade: declined for this phase.
- Optional auth in http mode: rejected, an unauthenticated remote memory server is a data leak.

## Consequences

Tool code is untouched apart from authorization. No server-side session state is kept.
