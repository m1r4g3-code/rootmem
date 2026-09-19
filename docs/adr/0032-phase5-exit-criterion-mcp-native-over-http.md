# ADR 0032: Phase 5's exit criterion is an MCP-native proof over real HTTP

**Status:** Accepted
**Date:** 2026-09-19

## Context

The value here is that identity and authorization hold over a real network transport, not that any benchmark improves.

## Decision

One automated test starts a real uvicorn server process in HTTP mode against real Postgres and exercises rejection without a token, continuity across two independent clients and a server restart, cross-identity denial, per-identity audit attribution, and stdio non-regression. No benchmark, REST facade, or TLS test.

## Alternatives considered

- An in-process ASGI test client only: rejected, it would not exercise the real process boundary or restart.

## Consequences

The test needs two identities created through the identity CLI/repository and a free local port.
