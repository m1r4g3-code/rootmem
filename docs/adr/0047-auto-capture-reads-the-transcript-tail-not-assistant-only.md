# ADR 0047: Auto-capture reads the transcript's tail, not `last_assistant_message` alone

**Status:** Accepted
**Date:** 2026-09-27

## Context

Found live, during the actual Phase 7 dogfooding pass this whole phase exists to pass: the user said "remember that the staging redeploy job runs every Tuesday at 3am," the assistant replied "Got it — noted" (deliberately not repeating the fact back, to keep the test clean), and a later recall query for it came back empty. Investigating the running server's request log showed `remember` calls firing correctly after every turn — the `Stop` hook mechanism worked — but the *content* stored was only ever the assistant's own reply. `build_record(last_assistant_message)`, as designed in ADR 0043, silently loses any fact the user stated when the assistant's own turn is a bare acknowledgement — which is exactly the common shape of "remember that X." This was a real design flaw, not a wiring problem, and the exit-criterion test's own synthetic payloads (`{"last_assistant_message": "..."}`) had accidentally been shaped to never expose it, because they never modeled the "state a fact, get a one-line ack" pattern.

## Decision

`claude_code_auto_capture.py` now reads `transcript_path` (already provided in `Stop`'s stdin payload) and reuses `claude_code_hook.py`'s existing `transcript_to_text` to take the transcript's tail (`DEFAULT_MAX_CHARS=4000`, small on purpose — this is a per-turn capture, not the full-session one `SessionEnd` already does) — capturing both the user's and the assistant's text for the just-finished exchange, not the assistant's alone.

## Alternatives considered

- Keep `last_assistant_message`, tell users to phrase acknowledgements more descriptively: rejected — it's not the user's job to work around a capture bug, and "remember that X" -> "Got it" is completely ordinary phrasing, not a misuse.
- A dedicated single-turn parser instead of reusing `transcript_to_text`: rejected for now — reuse is simpler and already tolerant/tested; a real limit (noted below) is accepted rather than solved with new code.

## Consequences

Auto-capture's per-turn write now costs one more file read (the transcript, already written to disk by Claude Code) — no new network calls. `transcript_to_text`'s truncation is character-based, not turn-aware, so a very long single turn could still be clipped oddly; `DEFAULT_MAX_CHARS` is a provisional size, not a tuned one. The exit-criterion test's synthetic payloads were rewritten to use real transcript files (mirroring `claude_code_hook.py`'s own test pattern) specifically so this class of bug is representable in the automated suite going forward, not just catchable by luck during a live pass.
