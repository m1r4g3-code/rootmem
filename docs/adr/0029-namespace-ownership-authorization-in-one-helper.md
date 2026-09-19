# ADR 0029: Authorization is namespace ownership, checked by one helper before any repository call

**Status:** Accepted
**Date:** 2026-09-19

## Context

Every tool takes a client-supplied `namespace`; `update` and `forget` take only a memory id. Over a remote transport a caller could otherwise read or change any namespace.

## Decision

A pure `authorize_namespace(identity, namespace)` decides ownership. A single `resolve_caller()` in the server reads the authenticated identity from the SDK's request context and every tool calls it first. stdio mode resolves to a fixed trusted local identity owning all namespaces, so behavior there is unchanged. `MemoryRepository.namespace_of(memory_id)` lets `update`/`forget` be authorized before mutating. A denied call performs no writes, including no audit entry.

## Alternatives considered

- Per-tool scopes (read/write): deferred.
- Deriving the namespace from the identity and ignoring the argument: rejected, breaks existing clients that pass explicit namespaces.

## Consequences

One new method on the memory repositories and a small change in each tool closure. A missing or foreign memory id answers "not found" to a non-owner, so existence is not leaked.
