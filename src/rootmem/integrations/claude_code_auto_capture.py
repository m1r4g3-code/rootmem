"""Claude Code `Stop` hook that automatically captures each finished turn
into ROOTMEM (ADR 0042/0043/0047) — independent of, and in addition to, the
end-of-session `SessionEnd` capture (`claude_code_hook.py`), which still
runs and still does the full transcript extraction this hook does not
attempt.

Configure it in `.claude/settings.json` (see docs/capture-hook-example.md):

    "command": "python -m rootmem.integrations.claude_code_auto_capture"

with `ROOTMEM_URL` and `ROOTMEM_TOKEN` in the environment (and optionally
`ROOTMEM_NAMESPACE`, `ROOTMEM_AUTO_CAPTURE_MIN_CHARS`,
`ROOTMEM_AUTO_CAPTURE_MAX_CHARS`). Claude Code passes a JSON object on
stdin containing `transcript_path`. This hook never blocks the turn ending:
on any failure, or when the turn is too short to be worth remembering, it
exits 0 without writing anything (ADR 0044). It always exits 0, even on
failure — a `Stop` hook's failure must not be allowed to interfere with the
turn actually finishing.

ADR 0047: this reads the transcript's tail (user *and* assistant text), not
just `last_assistant_message` (the first version's actual field, and its
bug) — found live, dogfooding this exact phase: a user stating a fact
plainly, answered with a bare acknowledgement that never repeats it back
("remember that X" -> "Got it"), stored nothing at all under the original
design, because only the assistant's own words were ever captured.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import TextIO

from rootmem.client import RootmemClient, RootmemError
from rootmem.integrations._env import env_int
from rootmem.integrations.claude_code_hook import transcript_to_text

# Deliberately short: a per-turn write must never noticeably delay a turn
# finishing (ADR 0044), regardless of the platform's own Stop-hook ceiling.
AUTO_CAPTURE_TIMEOUT_SECONDS = 8.0
DEFAULT_MIN_CHARS = 40
# Small on purpose: this captures roughly the last exchange, not the whole
# session (SessionEnd's `ingest_session` already does that, with full
# extraction). transcript_to_text keeps the *most recent* part when it
# truncates, so this reliably lands on the tail even for a long session.
DEFAULT_MAX_CHARS = 4000
SOURCE = "claude-code-auto-capture"


def _default_client(url: str, token: str) -> RootmemClient:
    return RootmemClient(url, token, timeout=AUTO_CAPTURE_TIMEOUT_SECONDS)


def build_record(transcript_lines: list[str], max_chars: int) -> str:
    """What gets stored: the tail of the transcript — both the user's and
    the assistant's text for (at least) the just-finished turn, trimmed.
    Deliberately not assistant-only (ADR 0047's finding)."""
    return transcript_to_text(transcript_lines, max_chars=max_chars).strip()


def run(
    stdin: TextIO,
    environ: dict[str, str],
    client_factory: Callable[[str, str], RootmemClient] = _default_client,
    stderr: TextIO = sys.stderr,
) -> int:
    url = environ.get("ROOTMEM_URL", "")
    token = environ.get("ROOTMEM_TOKEN", "")
    if not url or not token:
        print("rootmem auto-capture: ROOTMEM_URL and ROOTMEM_TOKEN must be set", file=stderr)
        return 0

    try:
        payload = json.loads(stdin.read() or "{}")
        transcript_path = str(payload["transcript_path"])
        lines = open(transcript_path, encoding="utf-8").read().splitlines()  # noqa: SIM115
    except (KeyError, ValueError, OSError) as exc:
        print(f"rootmem auto-capture: cannot read the transcript: {exc}", file=stderr)
        return 0

    max_chars = env_int(environ, "ROOTMEM_AUTO_CAPTURE_MAX_CHARS", DEFAULT_MAX_CHARS)
    record = build_record(lines, max_chars)
    min_chars = env_int(environ, "ROOTMEM_AUTO_CAPTURE_MIN_CHARS", DEFAULT_MIN_CHARS)
    if len(record) < min_chars:
        return 0

    namespace = environ.get("ROOTMEM_NAMESPACE", "default")
    try:
        client_factory(url, token).remember(record, source=SOURCE, namespace=namespace)
    except (RootmemError, OSError, TimeoutError) as exc:
        print(f"rootmem auto-capture: remember failed: {exc}", file=stderr)
        return 0
    return 0


def main() -> None:
    sys.exit(run(sys.stdin, dict(os.environ)))


if __name__ == "__main__":
    main()
