# Phase 7 Requirements — Auto-Memory Middleware

## Scope

Make ROOTMEM's read and write paths fire automatically around a Claude Code
session's own lifecycle, with no new server-side capability — reusing
`search`, `remember`, the REST facade and `RootmemClient` exactly as they
are today (see `docs/research/phase7-research-memo.md`).

## Functional requirements

- **FR1 — Automatic retrieval.** A `UserPromptSubmit` hook
  (`rootmem.integrations.claude_code_auto_recall`) calls `search` (via the
  REST client) with the submitted prompt text as the query, and — when at
  least one result scores above a configurable floor — injects a small,
  clearly labeled block of the top results as `additionalContext`, before
  Claude processes the prompt. No results, a request failure, or a timeout
  all produce no injected context and exit 0 — the prompt is never blocked,
  never delayed past a bounded ceiling, and its content is never altered.
- **FR2 — Automatic capture.** A `Stop` hook
  (`rootmem.integrations.claude_code_auto_capture`) calls `remember` with a
  short, formatted record of the just-finished turn (the user's prompt and
  the assistant's final message), gated by a minimum-length threshold so
  trivial turns are skipped. Any failure is best-effort: logged to stderr,
  exit 0, the user's session is never affected. **Implemented by reading
  `transcript_path`'s tail** (ADR 0047) — an earlier version that read only
  `last_assistant_message` from stdin technically satisfied "a record of
  the turn" but silently dropped the user's own words whenever the
  assistant's reply was a bare acknowledgement, found live during this
  phase's own dogfooding pass, not by inspection.
- **FR3 — Bounded latency, always.** Both hooks use a short, explicit
  client-side HTTP timeout (not the platform's default) and never retry.
  A slow or unreachable ROOTMEM server degrades to "no context injected" /
  "nothing captured this turn," never to a hung prompt or a failed turn.
- **FR4 — Configuration via environment**, matching the existing
  `SessionEnd` hook's own convention exactly: `ROOTMEM_URL`, `ROOTMEM_TOKEN`,
  `ROOTMEM_NAMESPACE` (default `"default"`), plus new
  `ROOTMEM_AUTO_RECALL_LIMIT` (default 3), `ROOTMEM_AUTO_RECALL_MIN_SCORE`
  (default 0.0 — accept the ranker's own ordering unless told otherwise),
  `ROOTMEM_AUTO_CAPTURE_MIN_CHARS` (default 40), `ROOTMEM_AUTO_CAPTURE_MAX_CHARS`
  (default 4000 — how much of the transcript's tail is captured; see FR2's
  note and ADR 0047).
- **FR5 — Read-scope safe.** The auto-recall hook only ever calls `search`
  (a read-scope tool). A token with `scope="read"` must work for auto-recall
  even if the deployment intentionally has no write access configured for
  that identity (auto-capture then simply fails per FR2/FR3, harmlessly).
- **FR6 — Docs and example config.** `docs/capture-hook-example.md` gains a
  worked `settings.json` snippet wiring all three hooks (`SessionEnd`,
  `UserPromptSubmit`, `Stop`) together, and states the FR4 env vars and the
  accepted duplicate-capture cost from the research memo.

## Non-functional requirements

- **NFR1 (latency).** The auto-recall hook must not meaningfully slow down
  prompt submission in the common case — bounded by its own configured HTTP
  timeout (default well under the UserPromptSubmit hook's own 30s ceiling).
- **NFR2 (no new dependency).** Both hooks are stdlib-plus-`RootmemClient`
  only, exactly like `claude_code_hook.py` — no new third-party package.
- **NFR3 (testability without a live server).** Both hooks' core logic
  (query/record construction, context-block formatting, threshold gating)
  is pure and unit-tested against an injectable client/transport, exactly
  like `claude_code_hook.py`'s `run()`/`client_factory` pattern — no test
  requires a real Claude Code process or a real HTTP server, except the
  exit-criterion test below.
- **NFR4 (honesty about cost).** The known Voyage-free-tier rate-limit
  interaction named in the research memo is documented in
  `docs/operations.md`, not hidden.

## Explicit non-goals

- A background/autonomous rumination or reconciliation process (the other
  half of the "closer to consciousness" work the user named; deferred to a
  later phase by their own explicit choice).
- Any new MCP tool, REST route, ranking term, or storage change — this
  phase is invocation-only.
- Deduplicating per-turn captures against the end-of-session transcript
  capture (accepted cost, see research memo).
- Support for any client other than Claude Code (the hook contract itself
  is Claude-Code-specific; a generic pattern for other clients is not
  designed here).
- Injecting context into anything other than plain text (no rendering of
  breakdown scores, entity links, etc. into the prompt — a short content
  preview only).

## Exit criterion (MCP/hook-native, no benchmark bar — matches Phase 0-6's own discipline)

One scenario, run against the two new hook entrypoints directly (calling
`run()` the same way `test_phase6_exit_criterion.py` calls the REST/MCP
tools directly, per NFR3) plus one real subprocess invocation:

1. A memory is written into a namespace (`remember`, or a prior turn's
   auto-capture). A synthetic `UserPromptSubmit` payload whose `prompt_text`
   overlaps that memory's content is fed to the auto-recall hook; its stdout
   is valid JSON with `hookSpecificOutput.additionalContext` containing that
   memory's content, and it exits 0.
2. A synthetic `UserPromptSubmit` payload with no overlap to anything stored
   produces no `additionalContext` at all (not an empty string — genuinely
   absent) and still exits 0.
3. A synthetic `Stop` payload naming a substantial transcript (a user fact
   plus a bare assistant acknowledgement — the shape that exposed ADR
   0047's bug) causes a new memory containing the *user's* fact to appear
   (provable via `search`/`recall` against the same namespace) with
   `source` distinguishing it as auto-captured.
4. A synthetic `Stop` payload naming a transcript below
   `ROOTMEM_AUTO_CAPTURE_MIN_CHARS` writes nothing.
5. Pointing either hook at an unreachable URL, or an expired/invalid token,
   produces the "safe no-op" behavior (FR1/FR2/FR3) and exits 0, never
   raising, never hanging past the configured timeout.
6. A read-scope-only token still lets auto-recall succeed (FR5); the same
   token used for auto-capture fails safely per (5)'s contract, not FR2's
   "success" contract — proving scope denial degrades the same way any
   other failure does.
7. `SessionEnd` behavior (the existing hook) is unchanged — a full
   regression pass of `test_phase6_exit_criterion.py` and the existing hook
   unit tests still passes untouched.
