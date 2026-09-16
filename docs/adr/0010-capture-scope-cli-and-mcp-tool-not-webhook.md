# ADR 0010: Capture scope — CLI entrypoint + MCP tool, not an HTTP webhook listener

**Status:** Accepted
**Date:** 2026-09-16

## Context

`src/rootmem/capture/README.md` (written in Phase 0, as a stub committing to rough future scope) describes the reserved capture layer as "session-lifecycle hooks, webhook capture, and batch import — the ingestion layer that feeds the extraction pipeline." Taken literally, "webhook capture" implies an HTTP server listening for inbound webhook requests. But Phase 0's requirements doc lists "REST API/remote transport" as a non-goal through Phase 5+, and ADR 0002 committed this project to stdio-only MCP transport specifically because that's how Claude Code and Cursor launch local MCP servers by default. Standing up any HTTP listener in Phase 1 — even one unrelated to MCP itself — would mean the first network-facing service this project has ever run, with its own security surface (authentication, input validation against untrusted inbound requests) that nothing else here has needed yet.

## Decision

Interpret "webhook capture" as *capture triggered by a client-side hook shelling out to a CLI*, not a network service ROOTMEM itself exposes. Concretely:

- `capture/cli.py` — a command-line entrypoint that a client-side hook (e.g. Claude Code's own `hooks.json` `SessionEnd` hook) can invoke directly, passing it a transcript to ingest.
- A new `ingest_session` MCP tool — the same ingestion path, reachable from within an active MCP session for in-session batch import.

No HTTP server, no listener, no inbound network exposure of any kind.

## Rationale

Both of the concrete capture use cases named in the Phase 0 stub — session-lifecycle hooks and batch import — are fully satisfiable without a network listener: a session-lifecycle hook is something the *client* (Claude Code/Cursor) already runs and can shell out from, and batch import is naturally a CLI or an in-session tool call, not something that needs an inbound HTTP endpoint to trigger. Building an actual webhook listener would be the first genuine scope violation of the standing "REST API/remote transport is Phase 5+" non-goal, for a capability this phase doesn't structurally need.

## Alternatives considered

- **A real HTTP webhook listener.** Rejected: conflicts directly with the standing REST API/remote-transport non-goal, and introduces a new class of security surface (inbound network requests) with no other phase or requirement demanding it yet.
- **CLI-only, no MCP tool.** Considered as the more minimal option — rejected because the marginal cost of also exposing `ingest_session` as an MCP tool is small, and keeping every capability reachable via MCP where practical matches this project's own stated integration philosophy (an agent already talking to ROOTMEM over MCP shouldn't need to shell out separately for something as core as ingesting a session).

## Consequences

- `docs/capture-hook-example.md` documents wiring a client-side `SessionEnd` hook to `python -m rootmem.capture.cli`, as the concrete example of what "session-lifecycle hooks" means under this interpretation.
- If a future phase genuinely needs inbound webhook delivery (e.g. from a third-party service ROOTMEM doesn't control the calling side of), that remains squarely Phase 5+ scope, requiring its own security review — not something this ADR's interpretation quietly backs into early.
