# ADR 0044: Both hooks are bounded-latency and best-effort — never block, never raise, never retry

**Status:** Accepted
**Date:** 2026-09-27

## Context

These hooks now run on *every prompt* and *every turn*, not once per session. A hung or slow ROOTMEM server (network hiccup, Voyage's free-tier 3-req/min ceiling, a revoked token) must never delay the user seeing a response or block them from typing the next prompt. `Stop` is documented as expected to complete before a turn is considered finished; rather than trust that ceiling exactly, both hooks are designed defensively regardless of the platform's precise blocking semantics — the same posture `claude_code_hook.py` already takes for `SessionEnd`.

## Decision

Both new hooks: (a) use a short, explicit client-side HTTP timeout, well under the platform's own default for the event; (b) never retry; (c) treat every failure mode — timeout, connection error, 401/403/429, empty result — as "nothing to inject" / "nothing captured this turn," logging to stderr and exiting 0, not as an error the user sees. A read-scope-only token causes auto-capture to fail this same safe way (write denied), which is accepted, not specially handled (ADR — Phase 7 requirements FR5).

## Alternatives considered

- Retrying within the hook: rejected — the whole point is a bounded ceiling; a retry loop risks exceeding it.
- Surfacing a failure to the user (exit 2 / a visible warning): rejected for capture (silent best-effort, matching `SessionEnd`'s own philosophy) and rejected for recall too — a missing memory is not an error condition worth interrupting a prompt over.

## Consequences

A real outage or a misconfigured token produces total silence, not a diagnosable error, unless someone inspects the hook's stderr (already the case for `SessionEnd`). This is a known, accepted tradeoff of "never block the user," restated in `docs/operations.md`.
