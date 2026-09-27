# Phase 7 Research Memo — Auto-Memory Middleware

**Question this phase answers:** every prior phase made ROOTMEM more capable
*when asked*. Nothing makes it act *without being asked* — an agent must
explicitly call `search`/`recall` to read, `remember`/`ingest_session` to
write. Human memory is not requested; it is ambient. The user asked, in plain
terms, for ROOTMEM to move a step closer to that — not by pretending to have
consciousness (see the Phase 6 follow-up conversation, recorded nowhere in
code, only in chat: mechanism, not experience), but by making the *mechanism*
operate automatically around the parts of a session where a human would
recall and register memories without deliberate effort.

## What already exists that this phase can reuse

Confirmed by direct read before writing this memo (not assumed):

- `search` (`integration/mcp/tools/search.py`) already degrades to text-only
  search if query embedding fails (rate limit, outage, no key) — it never
  raises on an embedding failure. This matters: an automatic, latency-bounded
  hook cannot tolerate an unbounded retry loop against Voyage's free-tier
  3-requests/minute ceiling, and it does not need to — degradation is already
  the contract.
- `remember` (`integration/mcp/tools/remember.py`) embeds synchronously
  inline and stores with `content_embedding = NULL` on failure (Phase 1
  behavior, unchanged). A write-path hook inherits the same bounded-latency,
  graceful-degradation behavior for free.
- `RootmemClient` (`client.py`) already has `.search()` and `.remember()`
  convenience methods, stdlib-only, injectable transport for tests.
- The `SessionEnd` hook (`integrations/claude_code_hook.py`) already proves
  the whole pattern end to end: stdin JSON → REST call with a bearer token →
  best-effort, non-blocking failure reported to stderr. Phase 7's two new
  hooks are siblings of this one, not a new pattern.
- **No new server-side capability is required.** Every piece Phase 7 needs
  (search, remember, the REST facade, the client) already exists and is
  already contract- and integration-tested. This phase is entirely about
  *automatic invocation* — new hook scripts plus the small pure logic that
  formats what they send/receive — not new storage, ranking, or provider
  code. That is a deliberately small footprint for a phase whose subject
  matter (making memory feel automatic) could otherwise balloon.

## What was verified about the Claude Code hook contract before designing

Verified live via the `claude-code-guide` agent (not assumed, since getting
this wrong breaks the feature outright):

- **`UserPromptSubmit`**: stdin JSON includes `prompt_text`, `session_id`,
  `transcript_path`, `cwd`. A hook injects context back into the conversation
  by printing `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
  "additionalContext": "..."}}` to stdout and exiting 0 — top-level
  `additionalContext` (not nested) is silently ignored. Default timeout 30s,
  overridable per-hook-entry via a `timeout` field in seconds. This is the
  injection point for auto-retrieval.
- **`Stop`**: fires after every assistant turn (not only session end), stdin
  includes `last_assistant_message`. Reported as synchronous — the hook is
  expected to complete before the turn is considered finished. Default
  timeout is longer (documented as 600s) but this phase does not trust an
  external HTTP round-trip (embedding + a database write) to reliably land
  under any fixed ceiling on every turn, so the write-path hook is designed
  to bound its own latency defensively (a short client timeout, treated as
  best-effort, never raising) rather than lean on the platform's exact
  blocking semantics — the same defensive posture already used for
  `SessionEnd`.
- Neither event supports a `matcher` field (they are not tool-specific).

## Design questions this memo resolves

**1. Where does automatic retrieval happen?** `UserPromptSubmit`. It is the
only event that both fires before Claude sees the prompt and supports
context injection — exactly the "recall before you answer" moment a human
has. No alternative event fits.

**2. Where does automatic capture happen?** `Stop`, not a new event and not
only `SessionEnd`. Capturing only at session end (today's behavior) means
nothing said three turns ago is available to `search` yet if the *same*
session asks about it again five turns later — no ambient within-session
recall. Capturing per-turn closes that gap. This is additive: `SessionEnd`'s
whole-transcript `ingest_session` capture (which also runs entity/relation
extraction over everything) is unchanged and still runs; per-turn capture
via `Stop` is a second, cheaper, immediate layer underneath it.

**3. Does per-turn capture duplicate the SessionEnd capture?** Yes, in part,
and this is accepted rather than engineered around this phase. A per-turn
raw episodic memory and the same content re-appearing inside the end-of-
session transcript ingest are exactly the kind of near-duplicate the
existing Phase 2 consolidation clustering already exists to merge — this
phase adds no new dedup logic and leans on that. Named as a real, accepted
cost (more rows, more embedding calls) in the requirements' non-goals, not
silently ignored.

**4. What gets written on every turn — is that too much, too expensive, too
noisy?** A raw `remember` call per turn, gated by a minimum-length threshold
(same `MIN_USEFUL_CHARS`-style guard the `SessionEnd` hook already uses,
so trivial turns like "ok" or a bare tool-result acknowledgement are
skipped). No LLM extraction happens per turn — extraction/distillation stays
where it already lives, inside `consolidate`, run in batch. This keeps the
per-turn cost to exactly one embedding call (already rate-limit-tolerant by
existing design) and one INSERT, matching the same cost profile `remember`
has always had; nothing new is invented, only invoked automatically.

**5. What gets injected on every prompt, and how much?** A small, fixed
number of top-`search`-ranked memories (default 3), each truncated to a
short preview, formatted as a clearly labeled block so the agent (and a
human reading the transcript) can tell it's retrieved context, not part of
the user's own message. Silence (no block at all) when nothing scores above
a floor or the request fails — never inject noise to "always show
something."

**6. What about cost/rate limits under real, active use?** Named plainly:
on Voyage's free tier (3 req/min), an active back-and-forth session doing a
search-embed on every prompt and a write-embed on every turn will exceed
that ceiling quickly. This is not a new problem Phase 7 introduces — it is
the same ceiling every prior phase's integration tests already had to pace
around — and the existing graceful-degradation behavior (text-only search,
null-embedding writes, later backfill) is the accepted mitigation, not a
new one built here. A paid Voyage tier removes the ceiling entirely. Stated
as an operational limit in the retro, not solved in code.

## What this phase deliberately does not attempt

The background rumination/reconciliation loop (an autonomous process that
revisits memory *without* a request at all, on its own schedule) is
explicitly the next, harder step, not this one (per the user's own choice
between the two options). Nothing here starts a background scheduler,
daemon, or cron-like process. Everything in Phase 7 is still triggered by a
real, externally-caused event (a prompt being submitted, a turn ending) —
it is automatic *invocation*, not autonomous *cognition*. That distinction,
raised in the Phase 6 follow-up conversation, is the one this phase is
careful not to blur: it makes memory access ambient to the user, not
self-directed for the agent.

## A real finding from building the exit criterion (not hypothesized in advance)

The design above assumed a fixed score floor (`ROOTMEM_AUTO_RECALL_MIN_SCORE`)
would let a genuinely unrelated prompt fall through with no injected context.
Live, this was false: with a real Voyage embedding in play, a completely
unrelated query ("what is the weather in reykjavik" against a stored memory
about a deploy key) still scored well above zero and got injected. Cosine
similarity between two arbitrary sentences is essentially never exactly
zero — a property of the embedding space itself, not a bug — so no fixed
floor on a blended, embedding-inclusive score can reliably separate "really
related" from "coincidentally the only memory in the namespace." The fix
adopted: auto-recall's `search` call uses `mode="text"`, which requires an
actual lexical match enforced in SQL, not just a low-ranked score — this
removes the false-positive class outright, at the honest cost of missing a
paraphrase sharing no words with what's stored. This is exactly the kind of
setback the user's own "build, then audit, then see setbacks" sequencing
was meant to surface, and it surfaced on the very first live-Postgres run of
the exit-criterion test, not from guesswork.

## A second real finding, from the actual live dogfooding pass

The automated exit-criterion test's own synthetic payloads for `Stop`
(`{"last_assistant_message": "..."}`) happened to model only the case where
the assistant's reply itself carries the content worth remembering — they
never modeled "user states a fact, assistant just acknowledges it," because
that shape didn't occur to be worth testing until it happened live. It did,
immediately: the user said "remember that the staging redeploy job runs
every Tuesday at 3am," the assistant replied "Got it — noted" (deliberately
not repeating the fact, to keep the test clean), and a later recall for it
came back empty. The server's own request log showed `remember` firing
correctly on every turn — the mechanism worked — but `build_record` only
ever looked at `last_assistant_message`, so nothing about the user's actual
words was ever captured. Fixed (ADR 0047) by reading `transcript_path`'s
tail instead, capturing both roles' text for the turn, and the exit-
criterion test itself was rewritten to use real transcript files precisely
so this class of bug is representable going forward rather than depending
on luck to be re-caught. This is the second concrete case, in the same
dogfooding session, of a design assumption that looked reasonable on paper
and was wrong the moment a real conversation exercised it — exactly the
value of the live pass over the automated proof alone.

## Revisit trigger for Phase 8+

Once this ships and is dogfooded, the honest next question is whether
per-turn auto-capture's duplicate-row cost is worth it in practice, or
whether it should be replaced by a cheaper "buffer the last N turns,
capture only if the session doesn't end cleanly" strategy — an open item,
not resolved here for lack of real usage data yet.
