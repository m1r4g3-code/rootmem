# ADR 0048: Auto-recall reads the real `prompt` field, not the assumed `prompt_text`

**Status:** Accepted
**Date:** 2026-09-27

## Context

The `UserPromptSubmit` hook contract used to design `claude_code_auto_recall.py` (research memo, ADR 0043) came from an agent's description of the contract, verified as carefully as could be done without a live payload in hand — it named the field `prompt_text`. It was wrong. Real captured invocations, gathered during this phase's own live dogfooding pass via a diagnostic wrapper that logged real stdin, show the field is actually named `prompt`. Because `payload.get("prompt_text")` on a real payload simply returns `None` — no exception, no error, nothing distinguishing it from "no relevant memory found" — **the hook had been silently doing nothing on every real prompt for the entire manual check**, while a parallel, separate verification (manually reproducing the same search via `curl`) gave a false impression that the mechanism worked end to end. That gap was caught by directly replaying a real captured payload through the actual `run()` function, not by re-reading the code.

## Decision

`claude_code_auto_recall.py` reads `payload.get("prompt") or payload.get("prompt_text") or ""` — `prompt` first, since that's what real invocations use; `prompt_text` kept as a free, harmless fallback in case a different Claude Code build or version uses it. Both the unit tests and the exit-criterion test were rewritten to use `prompt` as their primary payload shape, with one dedicated test keeping `prompt_text` covered as the fallback path.

## Alternatives considered

- Trusting the original agent-sourced contract description without live verification: this is exactly what produced the bug — an unverified secondhand description of an external system's wire format is not a substitute for observing a real instance of it, however carefully worded the description was.
- Silently fixing this without recording it: rejected — the whole reason the manual checklist caught it is that this project insists on checking what a mechanism actually does with real inputs rather than trusting what a synthetic test payload assumes about them; that discipline is worth naming, not hiding.

## Consequences

Every claim earlier in this phase's live pass that auto-recall was "confirmed working" from watching the conversation respond correctly was, in fact, unverified — the correct-looking answer came from the model's own conversational memory of the earlier turns in the same long conversation, not from the hook's injected context, which was empty the whole time. The manual checklist and retro were corrected before sign-off rather than left as originally drafted. The general lesson, worth carrying into any future hook or external-contract work: a description of a wire format, however carefully sourced, is not a substitute for replaying one real captured instance of it through the actual code before calling something verified.
