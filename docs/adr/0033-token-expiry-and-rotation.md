# ADR 0033: Tokens can expire and be rotated

**Status:** Accepted
**Date:** 2026-09-19

## Context

Phase 5 tokens never expire and cannot be replaced; a leaked token stays valid until an operator revokes the whole identity.

## Decision

`identities` gains `expires_at` (nullable). The verifier rejects an expired token on every request, like revocation. `rotate --name` replaces the stored digest with a new token's digest and prints the new token once; the old token stops working immediately. The identity keeps its name, namespaces, scope and audit history.

## Alternatives considered

- A grace window where both tokens work: rejected for now, it doubles the exposure a rotation is meant to end.
- Refresh tokens / OAuth: out of scope.

## Consequences

Expiry is optional per identity (default none), so existing identities are unaffected. Clients must be updated with the new token at rotation time.
