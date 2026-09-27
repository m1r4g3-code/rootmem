# ADR 0045: Phase 7 exit criterion is a hook-native proof, no benchmark bar

**Status:** Accepted
**Date:** 2026-09-27

## Context

Phase 0-6 each proved their exit criterion via direct calls into the real mechanism (MCP tool calls, HTTP calls) rather than a benchmark score, deferring real comparative evidence to a dedicated future effort the user has separately named (an atomic audit + rigorous benchmark pass, after more of the "closer to consciousness" work lands). Phase 7 follows the same discipline.

## Decision

The exit criterion calls the two new hooks' `run()` functions directly with synthetic stdin payloads shaped exactly like real Claude Code hook input (per the verified contract in the research memo), against an injectable client/transport for the pure-logic cases, plus one real subprocess + real HTTP server case mirroring `test_phase5/6_exit_criterion.py`'s harness, proving the actual entrypoint scripts work end-to-end at least once. No claim is made about response-quality or retrieval-quality improvement — that is explicitly out of scope until the later benchmark effort.

## Alternatives considered

- A real, interactive Claude Code session as the only proof: kept as the manual dogfooding companion (`scripts/manual_phase7_check.md`), not the automated gate — matches every prior phase's dual sign-off.
- Requiring a measured "response got better" number now: rejected — no benchmark harness exists yet, and building one prematurely, before the mechanism itself is even shipped, would be the same mistake named and rejected in ADR 0021/0026/0039.

## Consequences

Phase 7 ships on the same "mechanism proven, quality unmeasured" honesty as every phase before it. The revisit trigger is explicit: once the background-rumination phase also ships, both are due for the atomic-audit-then-benchmark pass the user described.
