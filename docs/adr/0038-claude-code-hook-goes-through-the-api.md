# ADR 0038: The Claude Code session hook goes through the API, not the database

**Status:** Accepted
**Date:** 2026-09-19

## Context

`docs/capture-hook-example.md` wires SessionEnd to `rootmem.capture.cli`, which opens the database directly with the server's credentials. That cannot serve a remote deployment and bypasses identity and audit.

## Decision

`integrations/claude_code_hook.py` reads the SessionEnd JSON from stdin, converts the transcript JSONL to text with a pure, tolerant parser, and calls `ingest_session` through the stdlib client using `ROOTMEM_URL` and `ROOTMEM_TOKEN`. It is therefore authenticated, authorized, rate-limited and audited like any other caller. The DB-direct CLI stays for local batch import.

## Alternatives considered

- Keeping only the DB-direct hook: rejected, wrong for remote use.
- A background daemon: rejected, a one-shot command is what hooks expect.

## Consequences

The hook needs a token and a reachable server. A failure never blocks the session ending: the script exits non-zero after logging and does not retry.
