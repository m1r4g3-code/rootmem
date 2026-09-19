# ADR 0027: An agent identity is a database row referenced by a hashed bearer token

**Status:** Accepted
**Date:** 2026-09-19

## Context

"Cross-instance identity continuity" was never defined. Nothing in the system is per-caller today.

## Decision

Continuity means: the same agent identity, from any client instance or machine, sees the same memory and is recorded as the actor of its writes, across restarts. It rests on a durable server-side `identities` row (`id`, `name`, `token_sha256`, `namespaces`, `created_at`, `revoked_at`). A token is 256 bits of randomness, shown once, stored only as its SHA-256 digest. An `IdentityRepository` Protocol (Postgres and in-memory) holds it.

## Alternatives considered

- Identity carried in client state or a client-chosen id: rejected, unauthenticated and not durable.
- OAuth/user login: rejected for this phase, far more surface than one agent needs.
- Slow password hashing for tokens: rejected, unnecessary for 256-bit random secrets.

## Consequences

Losing a token means issuing a new identity or token; there is no rotation feature yet. Revocation is immediate (checked per request).
