# ADR 0030: The audit actor is the authenticated identity

**Status:** Accepted
**Date:** 2026-09-19

## Context

ADR 0025 records an `actor` on every audit entry, but it was one constant (`settings.audit_actor`) because no caller identity existed.

## Decision

The actor recorded is the identity name resolved by `resolve_caller()`. In stdio mode it stays the configured local actor. The actor is part of the hashed row, so it cannot be altered without breaking the chain.

## Alternatives considered

- Actor as a client-supplied field: rejected, forgeable.

## Consequences

The recorder takes the actor per call rather than at construction.
