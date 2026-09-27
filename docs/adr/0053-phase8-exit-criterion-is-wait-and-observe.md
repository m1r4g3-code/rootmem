# ADR 0053: Phase 8's exit criterion is wait-and-observe, not call-and-response

**Status:** Accepted
**Date:** 2026-09-27

## Context

Every prior phase's exit criterion proved its mechanism by making a call and checking the response. That proves a request-driven mechanism works; it cannot prove an autonomous one does, because the entire claim being tested is "this happens with nobody calling anything." Phase 7's own retro named the general risk plainly: a verification that bypasses part of a pipeline can create false confidence that the pipeline itself works (ADR 0048's field-name bug slipped past exactly that way).

## Decision

The Phase 8 exit criterion seeds a scenario, starts a real server with rumination enabled and a short interval, **waits a bounded real duration making no tool call of any kind**, and only afterward makes one read-only call to observe what happened — the resolution must already have occurred before that call is made, not be triggered by it. A parallel check (a too-young contest, seeded to remain untouched) proves the pass is selective, not a blanket sweep run in response to the observing call itself.

## Alternatives considered

- Testing only the pure `decide_reconciliation` function and one `run_rumination_pass` call, treating the loop's wiring as too simple to need its own proof: rejected — Phase 7 showed directly that "simple wiring" (a stdin field name) is exactly where a real, invalidating bug hid; the loop's actual autonomous firing is this phase's entire point and gets its own real-subprocess, real-wait proof, not an assumption.
- Injecting a fake clock into the loop itself instead of waiting in real time: rejected for the loop-level test specifically — it would prove the pure logic again, not that a real `asyncio` task genuinely fires unprompted on a real timer inside a real process, which is the actual, novel claim.

## Consequences

This is the one exit-criterion test in the project that must include a real, if short (a few seconds), wall-clock wait — an explicit, accepted departure from every prior phase's "no sleeping in tests" discipline, justified by what's actually being proven.
