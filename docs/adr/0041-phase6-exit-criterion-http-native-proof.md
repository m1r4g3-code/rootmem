# ADR 0041: Phase 6's exit criterion is an HTTP-native proof with no measured number in the gate

**Status:** Accepted
**Date:** 2026-09-19

## Context

Phase 6 spans hardening, adapters, evaluation and packaging. The user confirmed an HTTP-native proof over a gate that includes a measured result.

## Decision

One automated test against a real uvicorn process and real Postgres covers expiry and rotation, scopes, rate limiting, health, REST parity, export/import, and the hook; the retrieval evaluation must run and write its report but its numbers are not gated. A live manual pass with a real client follows. The container build is verified in CI.

## Alternatives considered

- Gating on retrieval metrics: rejected, see ADR 0039.

## Consequences

The tag asserts the mechanisms work, not that ranking is good. The retro reports what the evaluation showed.
