# ADR 0026: Phase 4 exit criterion is a scoped MCP-native proof, no benchmark harness

**Status:** Accepted
**Date:** 2026-09-19

## Context

The source material measures ranking quality on benchmarks; no harness or usage corpus exists.

## Decision

Prove each mechanism (decay ordering, trust ordering, graph lift, audit validity and tamper detection) through MCP tool calls, as in ADR 0021. The user confirmed this scope over adding a small labeled retrieval benchmark.

## Alternatives considered

- A small labeled retrieval benchmark comparing old hybrid vs new ranking: declined for this phase.

## Consequences

Ranking quality is proven directional (orderings behave), not measured. Revisit trigger: real usage data or a benchmark harness becoming available.
