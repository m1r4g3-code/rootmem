from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from rootmem.client import RootmemClient
from rootmem.integrations.claude_code_auto_capture import SOURCE, build_record, run


def _line(role: str, content: Any, **extra: Any) -> str:
    return json.dumps({"type": role, "message": {"role": role, "content": content}, **extra})


def _write_transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_build_record_includes_the_users_own_words_not_just_the_assistants() -> None:
    """ADR 0047: a bare acknowledgement must not lose the user's own fact."""
    lines = [
        _line("user", "remember that the staging redeploy job runs every Tuesday at 3am"),
        _line("assistant", [{"type": "text", "text": "Got it, noted."}]),
    ]
    record = build_record(lines, max_chars=4000)
    assert "staging redeploy job runs every Tuesday at 3am" in record
    assert "Got it, noted" in record


class _RememberStub(RootmemClient):
    def __init__(self) -> None:
        super().__init__("http://h", "t", transport=lambda *_: (200, b"{}"))
        self.calls: list[dict[str, Any]] = []

    def remember(self, content: str, *, source: str, namespace: str = "default") -> dict[str, Any]:
        self.calls.append({"content": content, "source": source, "namespace": namespace})
        return {"id": "m-1", "created_at": "2026-09-27T00:00:00Z"}


def test_substantial_turn_is_captured_with_the_auto_capture_source(tmp_path: Path) -> None:
    path = _write_transcript(
        tmp_path,
        _line("user", "remember that the staging redeploy job runs every Tuesday at 3am"),
        _line("assistant", [{"type": "text", "text": "Got it, noted."}]),
    )
    stub = _RememberStub()
    err = io.StringIO()

    code = run(
        io.StringIO(json.dumps({"transcript_path": str(path)})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t", "ROOTMEM_NAMESPACE": "team"},
        client_factory=lambda *_: stub,
        stderr=err,
    )

    assert code == 0
    (call,) = stub.calls
    assert call["source"] == SOURCE
    assert call["namespace"] == "team"
    assert "staging redeploy job runs every Tuesday at 3am" in call["content"]


def test_short_turn_is_skipped_without_a_network_call(tmp_path: Path) -> None:
    path = _write_transcript(tmp_path, _line("user", "hi"), _line("assistant", "ok"))
    stub = _RememberStub()
    code = run(
        io.StringIO(json.dumps({"transcript_path": str(path)})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"},
        client_factory=lambda *_: stub,
        stderr=io.StringIO(),
    )
    assert code == 0
    assert stub.calls == []


def test_min_chars_is_configurable(tmp_path: Path) -> None:
    path = _write_transcript(tmp_path, _line("user", "short but flagged"))
    stub = _RememberStub()
    code = run(
        io.StringIO(json.dumps({"transcript_path": str(path)})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t", "ROOTMEM_AUTO_CAPTURE_MIN_CHARS": "5"},
        client_factory=lambda *_: stub,
        stderr=io.StringIO(),
    )
    assert code == 0
    assert len(stub.calls) == 1


def test_no_credentials_or_missing_transcript_never_raise_and_exit_zero(tmp_path: Path) -> None:
    err = io.StringIO()
    assert run(io.StringIO("{}"), {}, stderr=err) == 0
    assert "ROOTMEM_URL" in err.getvalue()

    env = {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"}
    missing = json.dumps({"transcript_path": str(tmp_path / "missing.jsonl")})
    assert run(io.StringIO(missing), env, stderr=io.StringIO()) == 0
    assert run(io.StringIO("not json"), env, stderr=io.StringIO()) == 0


def test_remember_failure_including_read_scope_denial_degrades_silently(tmp_path: Path) -> None:
    path = _write_transcript(
        tmp_path,
        _line("user", "a substantial turn that should normally be captured, past the length floor"),
    )
    failing = RootmemClient(
        "http://h",
        "t",
        transport=lambda *_: (
            403,
            json.dumps({"error": "scope 'read' does not permit 'remember'"}).encode(),
        ),
    )
    err = io.StringIO()

    code = run(
        io.StringIO(json.dumps({"transcript_path": str(path)})),
        {"ROOTMEM_URL": "http://h", "ROOTMEM_TOKEN": "t"},
        client_factory=lambda *_: failing,
        stderr=err,
    )

    assert code == 0
    assert "403" in err.getvalue()
