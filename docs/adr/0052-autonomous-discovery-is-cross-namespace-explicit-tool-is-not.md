# ADR 0052: Autonomous contest discovery is cross-namespace; the explicit tool stays namespace-scoped

**Status:** Accepted
**Date:** 2026-09-27

## Context

Every existing repository method and MCP tool takes a namespace because every existing caller is a namespace-scoped, authenticated request (`guarded`/`authorize_namespace`, ADR 0029). The autonomous rumination loop has no caller and no namespace to be scoped to — it serves the whole deployment.

## Decision

`GraphRepository.list_contested(namespace: str | None)` — `None` (used only by the autonomous loop) scans every namespace's contested relations directly; a specific namespace (used by the explicit `ruminate` tool, which still goes through `guarded`/`authorize_namespace` like every other tool) scopes to just that one. The loop itself is trusted server-side infrastructure, the same trust level as the `set_updated_at()` trigger or the audit hash-chain trigger — not a tenant-facing capability, and callable by no one.

## Alternatives considered

- Enumerating namespaces via the `identities` table first, then looping per-namespace: rejected — it would couple the graph layer to the identity layer for no benefit, and a namespace can exist with data but no identity currently pointing at it (e.g. mid-provisioning, or after a revoke).
- Giving the loop no cross-namespace capability at all, requiring an operator to configure a namespace list: rejected — it reintroduces exactly the kind of manual configuration burden an autonomous feature is supposed to remove.

## Consequences

`list_contested(None)` is the one place in this codebase a query legitimately crosses namespace boundaries outside of admin scripts. It is exercised only from the loop, never reachable through any MCP tool or REST route — confirmed by the contract tests and the exit criterion, which calls the explicit tool only with a namespace.
