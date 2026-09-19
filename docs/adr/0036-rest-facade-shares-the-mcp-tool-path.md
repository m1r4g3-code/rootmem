# ADR 0036: The REST facade calls the same tool path as MCP

**Status:** Accepted
**Date:** 2026-09-19

## Context

Non-MCP clients want plain HTTP. The SDK's `custom_route` handlers bypass bearer auth, and reimplementing authorization per route would create a second, divergent enforcement point.

## Decision

`GET /v1/tools` lists tools and `POST /v1/tools/{name}` runs one. The handler authenticates the Bearer header with the same `RootmemTokenVerifier`, sets the SDK's auth context, and calls the server's tool-call path, so scopes, namespace authorization, rate limits and audit are identical by construction. Errors map to 401, 403, 404, 422 and 429.

## Alternatives considered

- A hand-written route per tool: rejected, duplicates validation and authorization.
- Leaving REST out: declined by the user's theme choice.

## Consequences

REST inherits every future tool automatically. The REST API is the tool API, not a separately designed resource model.
