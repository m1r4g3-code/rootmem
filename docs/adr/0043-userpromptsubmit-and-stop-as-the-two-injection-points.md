# ADR 0043: `UserPromptSubmit` for retrieval, `Stop` for capture — not only `SessionEnd`

**Status:** Accepted
**Date:** 2026-09-27

## Context

`SessionEnd` already captures a whole transcript, once, at the end. That gives no within-session ambient recall: something said five turns ago is not searchable by `search` until the session is over. Verified against a live description of the Claude Code hook contract (via the `claude-code-guide` agent, not assumed) before committing to this: `UserPromptSubmit` fires before Claude sees a prompt and supports injecting `hookSpecificOutput.additionalContext`; `Stop` fires after every assistant turn, not only at session end.

## Decision

Automatic retrieval hooks off `UserPromptSubmit`: the prompt text becomes a `search` query, top results (if any score above a floor) are injected as `additionalContext`. Automatic capture hooks off `Stop`: each finished turn becomes a candidate `remember` call, gated by a minimum-length threshold. `SessionEnd`'s existing whole-transcript capture is unchanged and still runs — it still does the entity/relation extraction that per-turn capture deliberately does not attempt (see ADR 0044).

## Alternatives considered

- Capture only at `SessionEnd` (status quo): rejected as insufficient — it's exactly the gap this phase exists to close.
- `PostToolUse` for capture: rejected as the wrong event — it fires once per tool call, not once per conversational turn, and would fragment a single turn's meaning across many partial writes.

## Consequences

Per-turn capture and end-of-session capture will write overlapping content for the same conversation (accepted, see ADR-adjacent research memo; existing Phase 2 consolidation clustering is the intended path to merge near-duplicates, not new dedup logic here). Two new hook processes now run per turn instead of one per session — bounded latency for both is therefore load-bearing, not a nicety (ADR 0044).
