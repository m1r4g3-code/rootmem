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
