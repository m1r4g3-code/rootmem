# ADR 0042: Auto-memory middleware is client-lifecycle hooks over existing tools, not new server capability

**Status:** Accepted
**Date:** 2026-09-27

## Context

The user asked for memory use to stop being something the agent must decide to invoke — retrieval before a response, capture after one, invisibly. `search` already ranks and degrades gracefully; `remember` already writes and degrades gracefully; the REST facade and `RootmemClient` already expose both over HTTP with auth, scope and audit intact (ADR 0036/0038). Nothing about "automatic" requires new ranking, storage or provider code — only new *callers*.

## Decision

Phase 7 adds two new Claude Code hook entrypoints, siblings of the existing `SessionEnd` hook, each a thin script calling `RootmemClient.search`/`.remember` — no new MCP tool, REST route, schema field, or storage change. Automatic behavior is achieved entirely at the invocation layer.

## Alternatives considered

- A new `auto_recall`/`auto_capture` MCP tool pair: rejected — `search`/`remember` already do exactly what's needed; a wrapping tool would duplicate logic for no behavioral gain.
- Server-side automatic injection (the MCP server itself pushing context on every tool call): rejected — the server has no visibility into "a prompt was just submitted"; only the client's own hook lifecycle does.

## Consequences

All of Phase 7's engineering is in `integrations/`, not `storage/`, `retrieval/`, or `integration/mcp/`. Every existing contract test, ranking behavior and rate-limit/scope rule Phase 4-6 built is inherited unchanged; there is no new surface for those to regress against.
