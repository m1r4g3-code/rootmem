# Phase 7 Retrospective — Auto-Memory Middleware

**Status:** Filled in after `v0.7.0-phase7`'s automated exit-criterion test (passed, real Postgres), the full unit suite (355 passed) and free integration suite (104 passed, ~17 min), and a live manual pass with a real Claude Code session (8/8) on 2026-09-27 — a pass that found and fixed three real bugs, one severe enough to invalidate its own first, already-drafted "PASSED" write-up.

## What shipped

- **Two new Claude Code hooks, no new server capability (ADR 0042):** `claude_code_auto_recall` on `UserPromptSubmit` (injects relevant memories before Claude answers) and `claude_code_auto_capture` on `Stop` (writes a memory after each substantial turn), both thin callers of the existing `search`/`remember` tools via `RootmemClient`.
- **`mode="text"` for auto-recall specifically (ADR 0046):** an unattended, automatic gate can't rely on a blended semantic score to tell "related" from "coincidentally the only memory in the store" — cosine similarity between arbitrary sentences is essentially never zero. A real keyword match, enforced in SQL, is the actual gate.
- **Auto-capture reads the transcript's tail, not `last_assistant_message` (ADR 0047).**
- **Auto-recall reads the real `prompt` field, not the assumed `prompt_text` (ADR 0048).**
- Docs: research memo, requirements, 7 ADRs (0042-0048), math-spec stub, `docs/capture-hook-example.md`'s new "Automatic memory middleware" section, `docs/operations.md` cost/rate-limit notes.
- 21 hook unit tests, 1 real-Postgres exit-criterion test; `ruff`/`mypy --strict` clean across 203 files.

## What worked

- **Building with the same discipline as every other phase paid off even though this phase needed no new storage/ranking/provider code.** The exit-criterion test and unit tests existed before the live pass and caught nothing — every real bug here was found *only* by the live pass, which is exactly why the dual sign-off ritual (automated + manual) has never been optional.
- **The user's own sequencing call was right.** Building the mechanism first, then auditing it hard live (rather than trying to get it "perfect" on paper first) is what actually surfaced three real, non-obvious bugs in one sitting — no amount of additional code review would have caught the wrong stdin field name; only feeding it a real captured payload did.
- **Checking a live server's own request log, not just the conversation's apparent behavior, is what caught findings #1 and #3.** Both looked, from the outside, like "it's probably working" until the log was actually read.

## What didn't work / surprises

- **A "confirmation" obtained by manually reproducing part of a pipeline is not confirmation the pipeline works.** Reproducing the `search` call via `curl` to check what recall *should* find gave a false sense that auto-recall itself worked, when the actual hook code was silently broken (ADR 0048) the entire time. This is the single most important lesson from this phase: verify by replaying the *real, captured* input through the *actual* entrypoint, not by checking that the underlying data supports the answer.
- **An unverified, secondhand description of an external contract (Claude Code's own hook payload shape) was wrong**, despite being gathered carefully via a dedicated research step before writing any code. The field was `prompt`, not `prompt_text`. No amount of care in *asking* replaces one real observed instance of the thing being described.
- **An inline, multi-statement shell command (`python -c "...;...;..."`) was silently unreliable** for at least one hook event on this Windows setup, with no error surfaced anywhere. Root cause not fully isolated; a plain script-file invocation removed the risk class rather than explaining it.
- **Live-testing a feature inside the very engineering conversation that built it produces contaminated data** — an early test statement made before the fixes landed was permanently lost, and later captured content included large chunks of the assistant's own debugging narration rather than clean short turns, because turns in this conversation are technical essays, not chat messages. Not a product bug; a process lesson for next time (dogfood in a fresh, short session).

## Limits worth stating

- Auto-recall is lexical-only (`mode="text"`); it will not surface a memory that shares no words with the prompt, even if it's the semantically correct one.
- Per-turn auto-capture and the end-of-session `SessionEnd` capture write overlapping content for the same conversation, by design — left for Phase 2's consolidation clustering to merge, not deduplicated here.
- `DEFAULT_MAX_CHARS=4000` for auto-capture is character-based, not turn-aware — in a conversation with very long turns, the captured record can be dominated by earlier content rather than cleanly bounded to the latest exchange.
- This mechanism is Claude-Code-specific; no other client was tested or is supported by this hook contract.
- No background/autonomous cognition exists yet — everything here still runs only in response to a real Claude Code lifecycle event (a prompt, a turn ending), not on its own schedule. The user explicitly deferred that (a background rumination/reconciliation loop) to a later phase.
- The `prompt_text` fallback in `claude_code_auto_recall.py` is defensive, not verified against any real Claude Code build — only `prompt` has been observed live.

## Decisions to revisit in Phase 8+

- Whether relevance-only gating (via the ranked result's `breakdown` field, once the REST client exposes it) should replace or supplement `mode="text"`'s blunter keyword-match gate.
- Whether `DEFAULT_MAX_CHARS` needs to become turn-aware rather than character-based, once real usage (outside an engineering-heavy conversation) shows what a typical captured record actually looks like.
- The background rumination/reconciliation loop itself — the other half of the "closer to consciousness" work the user scoped this phase against, still not started.
- Carried unchanged from Phase 6: the q06 ranking regression, no shared rate limiter, no real benchmark evidence against competitors (named at length in the informal pre-Phase-7 conversation, not yet acted on).

## Metrics captured

- Unit tests: 355 passed (includes 21 hook-specific tests). Free integration suite: 104 passed (~1024s). Phase 7 exit-criterion test: 1 passed (real Postgres, no external API keys required — text-mode search needs no embedding call).
- `mypy --strict`: 203 files clean.
- Live: 3 real bugs found and fixed in one dogfooding session (ADR 0047, two distinct issues under ADR 0048's umbrella — the field name and the false-positive verification method); the manual checklist was drafted "PASSED" once, found to be wrong, and rewritten after the actual fix.
