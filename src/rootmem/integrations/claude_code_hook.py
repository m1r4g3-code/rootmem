"""Claude Code `SessionEnd` hook that ingests the finished session through the
REST API (ADR 0038), so it works against a remote, authenticated server.

Configure it in `.claude/settings.json` (see docs/capture-hook-example.md):

    "command": "python -m rootmem.integrations.claude_code_hook"

with `ROOTMEM_URL` and `ROOTMEM_TOKEN` in the environment (and optionally
`ROOTMEM_NAMESPACE`, `ROOTMEM_SOURCE`). Claude Code passes a JSON object on
stdin containing `transcript_path` and `session_id`. The hook never blocks
the session ending: on any failure it prints to stderr and exits non-zero
without retrying.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TextIO

from rootmem.client import RootmemClient, RootmemError

DEFAULT_MAX_CHARS = 20_000
MIN_USEFUL_CHARS = 20


def _text_of(content: Any) -> str:
    """Only human-readable text: plain strings and `text` blocks. Tool calls,
    tool results and hidden thinking are deliberately left out."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(block.get("text", "")).strip()
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def transcript_to_text(lines: Iterable[str], max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Turn Claude Code transcript JSONL into `role: text` paragraphs.

    Tolerant by design: blank lines, non-JSON lines, unknown record shapes and
    non-message records are skipped rather than failing the whole hook. If the
    result exceeds `max_chars`, the most recent part is kept (a session's
    conclusion matters more than its opening)."""
    paragraphs: list[str] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role") or record.get("type")
        if role not in ("user", "assistant"):
            continue
        text = _text_of(message.get("content"))
        if text:
            paragraphs.append(f"{role}: {text}")
    joined = "\n\n".join(paragraphs)
    if len(joined) > max_chars:
        joined = joined[-max_chars:]
    return joined


def run(
    stdin: TextIO,
    environ: dict[str, str],
    client_factory: Callable[[str, str], RootmemClient] = RootmemClient,
    stderr: TextIO = sys.stderr,
) -> int:
    url = environ.get("ROOTMEM_URL", "")
    token = environ.get("ROOTMEM_TOKEN", "")
    if not url or not token:
        print("rootmem hook: ROOTMEM_URL and ROOTMEM_TOKEN must be set", file=stderr)
        return 2
    try:
        payload = json.loads(stdin.read() or "{}")
        transcript_path = Path(str(payload["transcript_path"]))
        session_id = payload.get("session_id")
        text = transcript_to_text(transcript_path.read_text(encoding="utf-8").splitlines())
    except (KeyError, ValueError, OSError) as exc:
        print(f"rootmem hook: cannot read the session transcript: {exc}", file=stderr)
        return 1
    if len(text) < MIN_USEFUL_CHARS:
        return 0  # nothing worth remembering; not an error
    try:
        client_factory(url, token).ingest_session(
            text,
            source=environ.get("ROOTMEM_SOURCE", "claude-code"),
            namespace=environ.get("ROOTMEM_NAMESPACE", "default"),
            session_id=str(session_id) if session_id else None,
        )
    except (RootmemError, OSError) as exc:
        print(f"rootmem hook: ingest failed: {exc}", file=stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(run(sys.stdin, dict(os.environ)))


if __name__ == "__main__":
    main()
