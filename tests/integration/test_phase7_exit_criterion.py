"""The Phase 7 exit criterion (docs/requirements/phase7-requirements.md),
proven against a real uvicorn HTTP server and real Postgres, calling the
hook entrypoints' actual `run()` functions with the real `RootmemClient`
default (the same in-process-real-network pattern the Phase 6 hook proof
used for `claude_code_hook.py`).

(1)(2) auto-recall injects `additionalContext` when a stored memory
    overlaps the prompt, and prints nothing when it doesn't;
(3)(4) auto-capture writes a substantial turn and skips a trivial one;
(5) an unreachable server degrades both hooks to a silent no-op;
(6) a read-scope token still powers auto-recall; the same token used for
    auto-capture is denied the same safe way — nothing is written, nothing
    raises.

Marked `integration` (not `integration_external`): every query below finds
its fixture on plain lexical overlap (`mode="text"` / the default hybrid
mode's text-search fallback), so no Voyage or Anthropic call is required
for this proof to hold.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest

from rootmem.config import get_settings
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.integrations.claude_code_auto_capture import run as run_auto_capture
from rootmem.integrations.claude_code_auto_recall import run as run_auto_recall
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository
from tests.integration.test_phase5_exit_criterion import (
    _call,
    _client,
    _free_port,
    _HttpServer,
    _ok,
)

pytestmark = pytest.mark.integration


def _turn(tmp_path: Path, name: str, user_text: str, assistant_text: str) -> str:
    """A one-turn transcript file, ADR 0047-shaped: `auto_capture` reads
    both roles' text from `transcript_path`, not a `last_assistant_message`
    field alone (that was the original design's bug, found live)."""
    path = tmp_path / f"{name}.jsonl"
    assistant_content = [{"type": "text", "text": assistant_text}]
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": user_text}}),
        json.dumps(
            {"type": "assistant", "message": {"role": "assistant", "content": assistant_content}}
        ),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


@pytest.mark.asyncio
async def test_phase7_auto_recall_and_auto_capture_hooks(tmp_path: Path) -> None:
    suffix = uuid.uuid4().hex[:8]
    namespace = f"phase7-{suffix}"
    name_rw, name_ro = f"p7-writer-{suffix}", f"p7-reader-{suffix}"
    token_rw, token_ro = generate_token(), generate_token()

    pool = await create_pool(get_settings())
    server = _HttpServer(_free_port())
    try:
        identities = PostgresIdentityRepository(pool)
        await identities.create(name_rw, [namespace], hash_token(token_rw), scope="readwrite")
        await identities.create(name_ro, [namespace], hash_token(token_ro), scope="read")
        await server.start()
        base_url = f"http://127.0.0.1:{server.port}"
        base_env = {
            "ROOTMEM_URL": base_url,
            "ROOTMEM_TOKEN": token_rw,
            "ROOTMEM_NAMESPACE": namespace,
        }

        async with _client(server.url, token_rw) as client:
            _ok(
                await _call(
                    client,
                    "remember",
                    content="the deploy key rotates every friday",
                    source="phase7-test",
                    namespace=namespace,
                )
            )

        # --- (1) an overlapping prompt gets additionalContext injected ---
        out = io.StringIO()
        code = run_auto_recall(
            io.StringIO(json.dumps({"prompt": "when does the deploy key rotate?"})),
            base_env,
            stdout=out,
            stderr=io.StringIO(),
        )
        assert code == 0
        payload = json.loads(out.getvalue())
        context = payload["hookSpecificOutput"]["additionalContext"]
        assert "deploy key rotates every friday" in context

        # --- (2) an unrelated prompt injects nothing at all ---
        out_empty = io.StringIO()
        code = run_auto_recall(
            io.StringIO(json.dumps({"prompt": "what is the weather in reykjavik"})),
            base_env,
            stdout=out_empty,
            stderr=io.StringIO(),
        )
        assert code == 0
        assert out_empty.getvalue() == ""

        # --- (3) a substantial turn is auto-captured, attributed to the hook,
        # and includes the USER's own fact even though the assistant's reply
        # is a bare acknowledgement (ADR 0047 — the bug this fix addresses) ---
        fact = "the staging environment redeploys nightly at 2am"
        transcript = _turn(
            tmp_path, "turn3", user_text=f"remember that {fact}", assistant_text="Got it."
        )
        code = run_auto_capture(
            io.StringIO(json.dumps({"transcript_path": transcript})),
            base_env,
            stderr=io.StringIO(),
        )
        assert code == 0
        search_args = {"query": "staging redeploys nightly", "namespace": namespace, "mode": "text"}
        async with _client(server.url, token_rw) as client:
            found = _ok(await _call(client, "search", **search_args))
        assert any(
            fact in item["content"] and item["source"] == "claude-code-auto-capture"
            for item in found["results"]
        )

        # --- (4) a trivial turn writes nothing ---
        ack_query = {"query": "acknowledgement only", "namespace": namespace, "mode": "text"}
        async with _client(server.url, token_rw) as client:
            before = _ok(await _call(client, "search", **ack_query))
        trivial = _turn(tmp_path, "turn4", user_text="hi", assistant_text="ok")
        code = run_auto_capture(
            io.StringIO(json.dumps({"transcript_path": trivial})),
            base_env,
            stderr=io.StringIO(),
        )
        assert code == 0
        async with _client(server.url, token_rw) as client:
            after = _ok(await _call(client, "search", **ack_query))
        assert len(after["results"]) == len(before["results"])

        # --- (5) an unreachable server degrades both hooks to a silent no-op ---
        dead_env = {**base_env, "ROOTMEM_URL": f"http://127.0.0.1:{_free_port()}"}
        out_dead = io.StringIO()
        code = run_auto_recall(
            io.StringIO(json.dumps({"prompt": "anything"})),
            dead_env,
            stdout=out_dead,
            stderr=io.StringIO(),
        )
        assert code == 0
        assert out_dead.getvalue() == ""
        unreachable_transcript = _turn(
            tmp_path,
            "turn5",
            user_text="a substantial message that would otherwise be captured",
            assistant_text="acknowledged",
        )
        code = run_auto_capture(
            io.StringIO(json.dumps({"transcript_path": unreachable_transcript})),
            dead_env,
            stderr=io.StringIO(),
        )
        assert code == 0

        # --- (6) a read-scope token still powers auto-recall ... ---
        reader_env = {**base_env, "ROOTMEM_TOKEN": token_ro}
        out_reader = io.StringIO()
        code = run_auto_recall(
            io.StringIO(json.dumps({"prompt": "when does the deploy key rotate?"})),
            reader_env,
            stdout=out_reader,
            stderr=io.StringIO(),
        )
        assert code == 0
        assert "deploy key rotates every friday" in out_reader.getvalue()

        # ... but auto-capture with the same token is denied the same safe way.
        denied_transcript = _turn(
            tmp_path,
            "turn6",
            user_text="this write should be denied by scope alone, never by a crash",
            assistant_text="acknowledged",
        )
        err_reader = io.StringIO()
        code = run_auto_capture(
            io.StringIO(json.dumps({"transcript_path": denied_transcript})),
            reader_env,
            stderr=err_reader,
        )
        assert code == 0
        assert "403" in err_reader.getvalue() or "scope" in err_reader.getvalue().lower()
        denied_query = {"query": "denied by scope alone", "namespace": namespace, "mode": "text"}
        async with _client(server.url, token_rw) as client:
            denied_search = _ok(await _call(client, "search", **denied_query))
        assert denied_search["results"] == []
    finally:
        server.stop()
        await pool.close()
