# Wiring capture to a client-side session hook

ADR 0010 scopes `capture` to a CLI plus an MCP tool, never an inbound
webhook. Since Phase 6 there are two ways to run the CLI-style capture; pick by
where the server lives.

## Remote or authenticated server (recommended): the API hook

`rootmem.integrations.claude_code_hook` (ADR 0038) reads Claude Code's
`SessionEnd` JSON from stdin, turns the transcript into text, and ingests it
through the REST API with a bearer token. It is authenticated, authorized,
rate-limited and audited like any other caller, and it needs no database
credentials on the client.

```json
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [ { "type": "command",
                     "command": "python -m rootmem.integrations.claude_code_hook" } ] }
    ]
  }
}
```

Environment (set it where Claude Code runs):

| Variable | Meaning |
|---|---|
| `ROOTMEM_URL` | server base URL, e.g. `https://memory.example.com` |
| `ROOTMEM_TOKEN` | the identity's bearer token |
| `ROOTMEM_NAMESPACE` | target namespace (default `default`) |
| `ROOTMEM_SOURCE` | source label (default `claude-code`) |

Behavior: only user/assistant text is captured (tool calls, tool results and
hidden thinking are dropped); over 20,000 characters the most recent part is
kept; sessions with almost no text are skipped; any failure prints to stderr
and exits non-zero without retrying and without blocking the session ending.

## Automatic memory middleware (Phase 7): recall before, capture after every turn

The `SessionEnd` hook above captures a whole transcript once, at the end.
Two more hooks (ADR 0042/0043) make memory ambient *within* a session too —
the agent no longer decides to call `search`/`remember`; Claude Code's own
lifecycle triggers them automatically. Both share `SessionEnd`'s posture:
authenticated via the REST API, bounded-latency, and never allowed to block
or fail the session (ADR 0044) — a slow or unreachable server, an expired
token, or a read-only scope all degrade to "nothing happened this turn,"
never to a hung prompt or a broken turn.

```json
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [ { "type": "command",
                     "command": "python -m rootmem.integrations.claude_code_hook" } ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command",
                     "command": "python -m rootmem.integrations.claude_code_auto_recall",
                     "timeout": 10 } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command",
                     "command": "python -m rootmem.integrations.claude_code_auto_capture",
                     "timeout": 10 } ] }
    ]
  }
}
```

`ROOTMEM_URL`/`ROOTMEM_TOKEN`/`ROOTMEM_NAMESPACE` are shared with the
`SessionEnd` hook above. Additional variables:

| Variable | Default | Meaning |
|---|---|---|
| `ROOTMEM_AUTO_RECALL_LIMIT` | `3` | top-`N` memories considered for injection |
| `ROOTMEM_AUTO_RECALL_MIN_SCORE` | `0.0` | score floor below which nothing is injected |
| `ROOTMEM_AUTO_CAPTURE_MIN_CHARS` | `40` | a turn shorter than this is not captured |
| `ROOTMEM_AUTO_CAPTURE_MAX_CHARS` | `4000` | how much of the transcript's tail is captured per turn |

Two things worth knowing before turning this on:

- **Retrieval is lexical (`mode="text"`), not semantic.** Found live while
  proving this out: with a real embedding in play, cosine similarity between
  two *unrelated* sentences is essentially never exactly zero, so a
  fixed score floor on a semantic/hybrid search cannot reliably tell "really
  related" from "just the only memory in the store" — it kept injecting
  context for prompts that had nothing to do with what was stored. Requiring
  an actual keyword match (enforced in SQL, not just in the ranking) removes
  that false-positive class entirely, at the cost of missing a paraphrase
  that shares no words with what was stored. A read scope is sufficient for
  auto-recall.
- **Per-turn capture overlaps with `SessionEnd`'s own capture.** The same
  turn may be written twice — once immediately (raw, no extraction) and once
  again inside the end-of-session transcript (which also runs entity/relation
  extraction over everything). This is accepted, not deduplicated here;
  Phase 2's consolidation clustering is what eventually merges the
  near-duplicates. A write needs a `readwrite`-scope token; with a
  `read`-scope token, auto-capture fails the same safe, silent way as any
  other denial.
- **Auto-capture reads the transcript's tail (user and assistant text), not
  just the assistant's own reply** (ADR 0047). An earlier version stored
  only the assistant's message; found live, this silently lost the actual
  fact whenever the assistant's turn was a bare acknowledgement ("remember
  that X" -> "Got it") — an ordinary, common shape, not an edge case.

## Local database access: the direct CLI

`python -m rootmem.capture.cli` opens the database itself with the server's
own credentials, so it only makes sense on the machine that runs ROOTMEM.

```json
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [ { "type": "command",
        "command": "jq -r '.transcript_path' | xargs -I{} uv run python -m rootmem.capture.cli --source claude-code --file {}" } ] }
    ]
  }
}
```

## Cursor / other clients

Any client with a "run a command when a session ends" hook can pipe the
transcript text to either entry point. For bulk import of existing
transcripts, loop over files with the direct CLI:

```bash
for f in transcripts/*.txt; do
  uv run python -m rootmem.capture.cli --source batch-import --file "$f"
done
```
