from __future__ import annotations

import io
import json
from typing import Any

from rootmem.client import RootmemClient
from rootmem.integrations.claude_code_auto_recall import build_query, format_context, run


def test_build_query_strips_and_caps_length() -> None:
    assert build_query("  where is Alice employed  ") == "where is Alice employed"
    assert len(build_query("x" * 5000)) == 2000


def test_format_context_labels_namespace_and_truncates_long_content() -> None:
    results = [
        {"content": "short fact", "source": "manual"},
        {"content": "y" * 500, "source": "auto"},
    ]
    text = format_context(results, "team")

    assert text.startswith("[ROOTMEM memory — namespace 'team', retrieved automatically]")
    assert "1. (manual) short fact" in text
    assert "2. (auto) " + "y" * 239 + "…" in text


class _SearchStub(RootmemClient):
    def __init__(self, results: list[dict[str, Any]]) -> None:
        super().__init__("http://h", "t", transport=lambda *_: (200, b"{}"))
        self._results = results
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        query: str,
        *,
        namespace: str = "default",
        limit: int = 10,
        mode: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"query": query, "namespace": namespace, "limit": limit, "mode": mode})
        return {"results": self._results}


def test_injects_additional_context_when_results_score_above_floor() -> None:
    fact = {"content": "the deploy key rotates every friday", "source": "t", "score": 0.8}
    stub = _SearchStub([fact])
    out, err = io.StringIO(), io.StringIO()

    code = run(
        io.StringIO(json.dumps({"prompt": "when does the deploy key rotate?"})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t", "ROOTMEM_NAMESPACE": "team"},
        client_factory=lambda *_: stub,
        stdout=out,
        stderr=err,
    )

    assert code == 0
    payload = json.loads(out.getvalue())
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert "deploy key rotates every friday" in context
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    expected_call = {
        "query": "when does the deploy key rotate?",
        "namespace": "team",
        "limit": 3,
        "mode": "text",
    }
    assert stub.calls == [expected_call]


def test_no_results_or_below_floor_prints_nothing() -> None:
    stub = _SearchStub([{"content": "barely related", "source": "t", "score": 0.1}])
    out = io.StringIO()

    code = run(
        io.StringIO(json.dumps({"prompt": "anything"})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t", "ROOTMEM_AUTO_RECALL_MIN_SCORE": "0.5"},
        client_factory=lambda *_: stub,
        stdout=out,
        stderr=io.StringIO(),
    )

    assert code == 0
    assert out.getvalue() == ""


def test_real_claude_code_payload_shape_is_understood() -> None:
    """ADR 0048: the real field is `prompt`, confirmed against actual
    captured invocations -- not `prompt_text`, an earlier unverified
    assumption that silently found nothing on every real prompt."""
    fact = {"content": "the deploy key rotates every friday", "source": "t", "score": 0.8}
    stub = _SearchStub([fact])
    real_payload = (
        '{"session_id":"abc","transcript_path":"C:\\\\x.jsonl","cwd":"C:\\\\proj",'
        '"prompt_id":"p1","permission_mode":"bypassPermissions",'
        '"hook_event_name":"UserPromptSubmit","prompt":"when does the deploy key rotate?"}'
    )
    out = io.StringIO()
    code = run(
        io.StringIO(real_payload),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"},
        client_factory=lambda *_: stub,
        stdout=out,
        stderr=io.StringIO(),
    )
    assert code == 0
    assert "deploy key rotates every friday" in out.getvalue()


def test_prompt_text_is_accepted_as_a_defensive_fallback() -> None:
    stub = _SearchStub([{"content": "fallback fact", "source": "t", "score": 0.8}])
    out = io.StringIO()
    code = run(
        io.StringIO(json.dumps({"prompt_text": "fallback query"})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"},
        client_factory=lambda *_: stub,
        stdout=out,
        stderr=io.StringIO(),
    )
    assert code == 0
    assert "fallback fact" in out.getvalue()


def test_no_credentials_empty_prompt_or_bad_payload_never_raise_and_exit_zero() -> None:
    err = io.StringIO()
    assert run(io.StringIO("{}"), {}, stderr=err) == 0
    assert "ROOTMEM_URL" in err.getvalue()

    env = {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"}
    assert run(io.StringIO(json.dumps({"prompt": "   "})), env, stderr=io.StringIO()) == 0
    assert run(io.StringIO("not json"), env, stderr=io.StringIO()) == 0


def test_search_failure_degrades_silently_never_raises() -> None:
    failing = RootmemClient(
        "http://h",
        "t",
        transport=lambda *_: (401, json.dumps({"error": "revoked"}).encode()),
    )
    out, err = io.StringIO(), io.StringIO()

    code = run(
        io.StringIO(json.dumps({"prompt": "anything"})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"},
        client_factory=lambda *_: failing,
        stdout=out,
        stderr=err,
    )

    assert code == 0
    assert out.getvalue() == ""
    assert "401" in err.getvalue()


def test_malformed_numeric_env_falls_back_to_defaults_instead_of_crashing() -> None:
    stub = _SearchStub([{"content": "fact", "source": "t", "score": 0.9}])
    code = run(
        io.StringIO(json.dumps({"prompt": "q"})),
        {
            "ROOTMEM_URL": "http://h",
            "ROOTMEM_TOKEN": "t",
            "ROOTMEM_AUTO_RECALL_LIMIT": "not-a-number",
            "ROOTMEM_AUTO_RECALL_MIN_SCORE": "also-not-a-number",
        },
        client_factory=lambda *_: stub,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert code == 0
    assert stub.calls[0]["limit"] == 3  # DEFAULT_LIMIT, not a crash
