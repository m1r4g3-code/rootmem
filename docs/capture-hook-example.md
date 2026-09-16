# Wiring capture to a client-side session hook

ADR 0010 deliberately scopes `capture` to a CLI entrypoint plus an MCP tool
— never an HTTP webhook listener ROOTMEM itself exposes. "Session-lifecycle
hooks" (the capability `src/rootmem/capture/README.md` originally promised)
means *the client* triggers ingestion by shelling out to
`rootmem.capture.cli`, not ROOTMEM listening for inbound requests.

## Claude Code

Claude Code supports a `SessionEnd` hook in its settings
(`.claude/settings.json` or `~/.claude/settings.json`) that runs a shell
command when a session ends, receiving the session's transcript path on
stdin as JSON (see Claude Code's own hooks documentation for the exact
payload shape). A minimal wiring:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.transcript_path' | xargs -I{} uv run python -m rootmem.capture.cli --source claude-code --file {}"
          }
        ]
      }
    ]
  }
}
```

This extracts the transcript file path from the hook's JSON payload and
passes it to `capture/cli.py` via `--file`, which reads it, ingests it
(embed, store, extract, materialize into the graph), and prints an
`IngestResult` as JSON — visible in the hook's own logs, not surfaced back
into the conversation.

## Cursor / other clients

Any client with an equivalent "run a command when a session/conversation
ends" hook can be wired the same way: get the transcript text onto stdin or
into a file, invoke `uv run python -m rootmem.capture.cli --source <client-name>
--file <path>` (or pipe to stdin without `--file`).

## Batch import

For importing existing transcripts in bulk (not tied to a live session),
just loop over files directly:

```bash
for f in transcripts/*.txt; do
  uv run python -m rootmem.capture.cli --source batch-import --file "$f"
done
```
