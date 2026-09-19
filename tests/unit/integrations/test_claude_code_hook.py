from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from rootmem.client import RootmemClient
from rootmem.integrations.claude_code_hook import run, transcript_to_text


def _line(role: str, content: Any, **extra: Any) -> str:
    return json.dumps({"type": role, "message": {"role": role, "content": content}, **extra})


def test_extracts_user_and_assistant_text_only() -> None:
    lines = [
        _line("user", "How do I fix the flaky test?"),
        _line(
            "assistant",
            [
                {"type": "thinking", "thinking": "private reasoning"},
                {"type": "text", "text": "Pin the clock in the fixture."},
                {"type": "tool_use", "name": "Edit", "input": {"file": "x.py"}},
            ],
        ),
        _line("user", [{"type": "tool_result", "content": "big tool output"}]),
        _line("assistant", [{"type": "text", "text": "Done, the test is stable."}]),
    ]

    text = transcript_to_text(lines)

    assert text == (
        "user: How do I fix the flaky test?\n\n"
        "assistant: Pin the clock in the fixture.\n\n"
        "assistant: Done, the test is stable."
    )
    assert "private reasoning" not in text and "tool output" not in text


def test_tolerates_garbage_blank_and_non_message_records() -> None:
    lines = [
        "",
        "not json at all",
        "[1, 2, 3]",
        json.dumps({"type": "summary", "summary": "x"}),
        json.dumps({"type": "system", "message": {"role": "system", "content": "hidden"}}),
        _line("user", "kept"),
    ]
    assert transcript_to_text(lines) == "user: kept"


def test_long_transcripts_keep_the_most_recent_part() -> None:
    lines = [_line("user", "old " * 500), _line("assistant", "the conclusion")]
    text = transcript_to_text(lines, max_chars=100)
    assert len(text) == 100
    assert text.endswith("the conclusion")


class _RecordingClient(RootmemClient):
    def __init__(self, url: str, token: str) -> None:
        super().__init__(url, token, transport=lambda *_: (200, b"{}"))
        self.ingested: list[dict[str, Any]] = []

    def ingest_session(self, transcript: str, **kwargs: Any) -> dict[str, Any]:
        self.ingested.append({"transcript": transcript, **kwargs})
        return {}


def _write_transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_run_ingests_through_the_client_with_env_settings(tmp_path: Path) -> None:
    path = _write_transcript(
        tmp_path, _line("user", "remember that staging deploys are on Thursday afternoons")
    )
    created: list[_RecordingClient] = []

    def factory(url: str, token: str) -> RootmemClient:
        client = _RecordingClient(url, token)
        created.append(client)
        return client

    code = run(
        io.StringIO(json.dumps({"transcript_path": str(path), "session_id": "s-1"})),
        {
            "ROOTMEM_URL": "http://h:1",
            "ROOTMEM_TOKEN": "rmk_t",
            "ROOTMEM_NAMESPACE": "team",
            "ROOTMEM_SOURCE": "cc",
        },
        client_factory=factory,
        stderr=io.StringIO(),
    )

    assert code == 0
    (call,) = created[0].ingested
    assert call["source"] == "cc" and call["namespace"] == "team" and call["session_id"] == "s-1"
    assert "staging deploys are on Thursday" in call["transcript"]


def test_run_without_credentials_or_with_unreadable_transcript_fails_without_raising(
    tmp_path: Path,
) -> None:
    err = io.StringIO()
    assert run(io.StringIO("{}"), {}, stderr=err) == 2
    assert "ROOTMEM_URL" in err.getvalue()

    err = io.StringIO()
    payload = json.dumps({"transcript_path": str(tmp_path / "missing.jsonl")})
    env = {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"}
    assert run(io.StringIO(payload), env, stderr=err) == 1
    assert run(io.StringIO("not json"), env, stderr=io.StringIO()) == 1


def test_trivial_sessions_are_skipped_and_server_errors_do_not_raise(tmp_path: Path) -> None:
    env = {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"}
    tiny = _write_transcript(tmp_path, _line("user", "hi"))
    called: list[str] = []

    def factory(url: str, token: str) -> RootmemClient:
        called.append("built")
        return RootmemClient(url, token, transport=lambda *_: (200, b"{}"))

    payload = json.dumps({"transcript_path": str(tiny)})
    assert run(io.StringIO(payload), env, client_factory=factory, stderr=io.StringIO()) == 0
    assert called == []  # nothing worth remembering, no network call

    big = _write_transcript(tmp_path, _line("user", "a substantial session worth remembering"))

    def failing(url: str, token: str) -> RootmemClient:
        return RootmemClient(
            url,
            token,
            transport=lambda *_: (401, json.dumps({"error": "authentication required"}).encode()),
        )

    err = io.StringIO()
    payload = json.dumps({"transcript_path": str(big)})
    assert run(io.StringIO(payload), env, client_factory=failing, stderr=err) == 1
    assert "401" in err.getvalue()
