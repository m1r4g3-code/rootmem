"""Claude Code `UserPromptSubmit` hook that automatically retrieves relevant
memories from ROOTMEM before Claude sees the prompt (ADR 0042/0043), and
injects them as `hookSpecificOutput.additionalContext`.

Configure it in `.claude/settings.json` (see docs/capture-hook-example.md):

    "command": "python -m rootmem.integrations.claude_code_auto_recall"

with `ROOTMEM_URL` and `ROOTMEM_TOKEN` in the environment (and optionally
`ROOTMEM_NAMESPACE`, `ROOTMEM_AUTO_RECALL_LIMIT`,
`ROOTMEM_AUTO_RECALL_MIN_SCORE`). Claude Code passes a JSON object on stdin
containing `prompt` (ADR 0048 — confirmed against real captured
invocations; an earlier, unverified description of the contract said
`prompt_text`, which is silently wrong: nothing about it errors, it just
never finds anything). This hook never blocks the prompt: on any failure,
or when nothing scores above the floor, it prints nothing and exits 0
(ADR 0044) — the absence of injected context is a normal, silent outcome,
not an error. It always exits 0, even on failure: `UserPromptSubmit` treats
a non-zero exit as a reason to deny the prompt, which this hook must never
do.

Retrieval uses `mode="text"` (lexical match required in SQL), not the
default hybrid/semantic search — found live, during the Phase 7 exit
criterion, that a genuinely unrelated prompt still scored above any fixed
floor once a real embedding was involved: cosine similarity between two
arbitrary sentences is essentially never exactly zero. See the inline note
at the search call.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import Any, TextIO

from rootmem.client import RootmemClient, RootmemError
from rootmem.integrations._env import env_float, env_int

# Well under the platform's own 30s default for this event (ADR 0044) — a
# slow or rate-limited server should degrade to "no context", not delay the
# user's prompt.
AUTO_RECALL_TIMEOUT_SECONDS = 8.0
DEFAULT_LIMIT = 3
DEFAULT_MIN_SCORE = 0.0
MAX_QUERY_CHARS = 2000
PREVIEW_CHARS = 240


def _default_client(url: str, token: str) -> RootmemClient:
    return RootmemClient(url, token, timeout=AUTO_RECALL_TIMEOUT_SECONDS)


def build_query(prompt_text: str) -> str:
    """The search query is the prompt itself, capped so an unusually long
    prompt (e.g. a pasted file) doesn't blow past a reasonable request size."""
    return prompt_text.strip()[:MAX_QUERY_CHARS]


def format_context(results: list[dict[str, Any]], namespace: str) -> str:
    """Pure formatting: a short, clearly labeled block naming its own
    origin, so it's never mistaken for part of the user's own message."""
    lines = [f"[ROOTMEM memory — namespace '{namespace}', retrieved automatically]"]
    for i, item in enumerate(results, start=1):
        content = str(item.get("content", "")).strip().replace("\n", " ")
        if len(content) > PREVIEW_CHARS:
            content = content[: PREVIEW_CHARS - 1] + "…"
        lines.append(f"{i}. ({item.get('source', '?')}) {content}")
    return "\n".join(lines)


def run(
    stdin: TextIO,
    environ: dict[str, str],
    client_factory: Callable[[str, str], RootmemClient] = _default_client,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    url = environ.get("ROOTMEM_URL", "")
    token = environ.get("ROOTMEM_TOKEN", "")
    if not url or not token:
        print("rootmem auto-recall: ROOTMEM_URL and ROOTMEM_TOKEN must be set", file=stderr)
        return 0  # never blocks the prompt; just nothing to inject

    try:
        payload = json.loads(stdin.read() or "{}")
    except ValueError as exc:
        print(f"rootmem auto-recall: cannot read hook payload: {exc}", file=stderr)
        return 0
    # ADR 0048: the real payload's field is "prompt", confirmed against
    # actual captured Claude Code invocations, not "prompt_text" as an
    # earlier, unverified description of the contract had it -- that
    # earlier assumption meant this hook silently found nothing on every
    # real prompt until this was caught. "prompt_text" is kept as a second
    # try in case a different Claude Code build uses it; it costs nothing.
    raw_prompt = payload.get("prompt") or payload.get("prompt_text") or ""
    query = build_query(str(raw_prompt))
    if not query:
        return 0

    namespace = environ.get("ROOTMEM_NAMESPACE", "default")
    limit = env_int(environ, "ROOTMEM_AUTO_RECALL_LIMIT", DEFAULT_LIMIT)
    min_score = env_float(environ, "ROOTMEM_AUTO_RECALL_MIN_SCORE", DEFAULT_MIN_SCORE)

    try:
        # mode="text", not the default "hybrid": found live (the Phase 7 exit
        # criterion) that an unrelated prompt still scored above any fixed
        # floor once a real Voyage embedding was in play — cosine similarity
        # between two arbitrary sentences is essentially never exactly zero,
        # so a blended, embedding-inclusive score cannot reliably tell
        # "genuinely related" from "the only memory in the store". Requiring
        # an actual lexical match (enforced in SQL, not just score-ordered)
        # eliminates that false-positive class entirely; a paraphrase with no
        # shared words is missed as a real, accepted cost of automatic,
        # unattended gating (see ADR 0044's follow-up note).
        response = client_factory(url, token).search(
            query, namespace=namespace, limit=limit, mode="text"
        )
    except (RootmemError, OSError, TimeoutError) as exc:
        print(f"rootmem auto-recall: search failed: {exc}", file=stderr)
        return 0

    results = [r for r in response.get("results", []) if r.get("score", 0.0) >= min_score]
    if not results:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": format_context(results, namespace),
                }
            }
        ),
        file=stdout,
    )
    return 0


def main() -> None:
    sys.exit(run(sys.stdin, dict(os.environ)))


if __name__ == "__main__":
    main()
