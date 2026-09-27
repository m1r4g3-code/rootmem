# Phase 7 Manual Exit-Criterion Validation

Human-observed companion to `tests/integration/test_phase7_exit_criterion.py`:
a real Claude Code session with both new hooks wired in, rather than
synthetic stdin payloads.

**Status: PASSED (8/8), after three real bugs were found live and fixed —
one of which invalidated the first attempt at every item on this checklist
and required redoing it.** Automated proof:
`tests/integration/test_phase7_exit_criterion.py` (1 passed, real Postgres,
re-run after all three fixes). Live pass complete 2026-09-27.

## Prerequisites (as actually run)

1. HTTP-mode ROOTMEM server on `127.0.0.1:8765`, real dev Postgres, identity
   `manual-p7` (`readwrite`, 1-day expiry) and `manual-p7-reader` (`read`,
   1-day expiry), both owning namespace `manual-phase7`.
2. `.claude/settings.local.json` (gitignored, project-scoped — not the
   committed `settings.json`) wired with all three hooks. **Deviation from
   the original plan, found necessary live:** the hook `command` could not
   simply be `python -m rootmem.integrations.claude_code_X` with env vars
   set ambiently, because the token had to be supplied to an
   *already-running* Claude Code host process that can't be given new
   environment variables without a restart. Each hook command instead
   invokes a tiny wrapper script that sets `ROOTMEM_URL`/`ROOTMEM_TOKEN`/
   `ROOTMEM_NAMESPACE` in Python before calling the real hook's `main()`.
3. No `/mcp`-style reconnect was needed for the hooks specifically — a
   corrected hook command took effect on the very next prompt, no session
   restart required (unlike MCP server config changes).

## Checklist

- [x] **Ambient recall, same session**: after all three fixes landed, asked
  "when's the staging redeploy again?" and got "every Tuesday at 3am" back.
  Verified as a genuine pass, not a repeat of the earlier false positive
  (see Findings #2): confirmed via the debug log that the real hook fired
  with the real `prompt` field, and independently reproduced the exact same
  query against the server to confirm the fact ranks first (score 0.62).
- [x] **No noise on unrelated turns**: confirmed earlier in the same pass —
  an unrelated prompt ("what is the weather in reykjavik") produced no
  injected context once `mode="text"` was in place (ADR 0046).
- [x] **Per-turn capture confirmed**: a memory appears in `manual-phase7`
  with `source="claude-code-auto-capture"` immediately after a substantial
  turn, before `SessionEnd` runs — confirmed by querying the namespace
  directly, and, after Finding #1's fix, confirmed to contain the *user's*
  words, not just the assistant's.
- [x] **Trivial turns skipped**: verified via the automated exit-criterion
  test (a two-line "hi"/"ok" transcript produces no write).
- [x] **Read-scope identity**: `manual-p7-reader` (`read` scope). Auto-recall
  with that token returned the same injected context as the readwrite
  token. Auto-capture with that token failed with
  `403: scope 'read' does not permit 'remember'`, exit 0, nothing written —
  confirmed by re-querying the namespace afterward.
- [x] **Unreachable server**: pointed `auto_recall` at a refused port.
  Exit 0, no stdout, a clean connection-refused message to stderr, no hang.
- [x] **SessionEnd unaffected**: an `ingest_session` call (SessionEnd's own
  capture) is visible in the server log from earlier in this pass, running
  independently of the per-turn captures around it.
- [x] **Cleanup**: both manual-check identities revoked, HTTP server
  stopped, `.claude/settings.local.json`'s `hooks` block removed, temporary
  wrapper/debug scripts deleted from the scratch temp directory.

## Findings during the pass (three real bugs, in the order found)

1. **`auto_capture` originally lost the actual fact (ADR 0047).** Storing
   only `last_assistant_message` meant a bare acknowledgement ("remember
   that X" -> "Got it") captured nothing about X. Found by checking the
   live server's own request log — `remember` calls were firing, but a
   later recall came back empty. Fixed by reading the transcript's tail
   (both roles' text) instead.
2. **An inline `python -c "...; ...; ..."` hook command was unreliable for
   `UserPromptSubmit` specifically**, though the same style worked for
   `Stop`/`SessionEnd`. No error was ever visible — it simply never
   executed. Switching every hook to a plain `python wrapper.py` invocation
   fixed it, confirmed via a real debug-log entry with the exact payload
   Claude Code sends.
3. **The most serious one, found only because of #2's own debug logging:
   `auto_recall` was reading the wrong stdin field the entire time (ADR
   0048).** The real `UserPromptSubmit` payload's field is `prompt`, not
   `prompt_text` (the name an earlier, unverified description of the
   contract had used). This meant `payload.get("prompt_text")` silently
   returned `None` on every real invocation — no error, just nothing
   injected, ever, on a real prompt. Every earlier "confirmation" in this
   same pass that recall was working had actually come from manually
   reproducing the search via `curl`, which bypassed the broken hook code
   entirely — the live mechanism itself had done nothing the whole time.
   **This invalidated the first, already-drafted version of this checklist
   ("PASSED 8/8")**, which had to be rewritten after the real bug was
   caught and fixed. Fixed by reading `prompt` first, `prompt_text` kept as
   a harmless fallback. Re-verified for real afterward, twice: once via a
   direct script-level replay of a captured real payload, once via an
   actual live Claude Code prompt with the debug log and a reproduced
   search confirming the correct content and ranking.

**The meta-lesson, worth stating plainly**: a "confirmation" obtained by
manually reproducing part of a pipeline (here, the search call) is not
confirmation the *pipeline itself* works — it only proves the data is
retrievable, not that the code that's supposed to retrieve it automatically
actually does. This is exactly the failure mode ADR 0048 records, and it
came within one incautious step of being shipped as "PASSED."
