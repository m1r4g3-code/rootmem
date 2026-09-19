from __future__ import annotations

import json

import pytest

from rootmem.client import RootmemClient, RootmemError


class _FakeTransport:
    def __init__(self, status: int = 200, body: object = None) -> None:
        self.status = status
        self.body = body if body is not None else {"result": {"ok": True}}
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, bytes]:
        self.calls.append((method, url, headers, body))
        return self.status, json.dumps(self.body).encode()


def test_call_sends_bearer_json_to_the_tool_endpoint() -> None:
    transport = _FakeTransport(body={"result": {"id": "m1"}})
    client = RootmemClient("http://host:1/", "rmk_tok", transport=transport)

    result = client.remember("hello", source="me", namespace="ns")

    assert result == {"id": "m1"}
    method, url, headers, body = transport.calls[0]
    assert (method, url) == ("POST", "http://host:1/v1/tools/remember")
    assert headers["Authorization"] == "Bearer rmk_tok"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body or b"") == {"content": "hello", "source": "me", "namespace": "ns"}


def test_typed_helpers_build_the_right_arguments() -> None:
    transport = _FakeTransport()
    client = RootmemClient("http://h", "t", transport=transport)

    client.search("q", namespace="n", limit=3)
    client.recall("abc", namespace="n")
    client.ingest_session("text", source="s", namespace="n", session_id="sess")

    bodies = [json.loads(call[3] or b"") for call in transport.calls]
    assert bodies[0] == {"query": "q", "namespace": "n", "limit": 3}
    assert bodies[1] == {"id": "abc", "namespace": "n"}
    assert bodies[2] == {
        "transcript": "text",
        "source": "s",
        "namespace": "n",
        "session_id": "sess",
    }


def test_list_tools_uses_get_without_a_body() -> None:
    transport = _FakeTransport(body=[{"name": "search"}])
    tools = RootmemClient("http://h", "t", transport=transport).list_tools()
    assert tools == [{"name": "search"}]
    assert transport.calls[0][0] == "GET" and transport.calls[0][3] is None


@pytest.mark.parametrize("status", [401, 403, 404, 422, 429, 500])
def test_error_statuses_raise_with_the_server_message(status: int) -> None:
    client = RootmemClient("http://h", "t", transport=_FakeTransport(status, {"error": "nope"}))
    with pytest.raises(RootmemError) as excinfo:
        client.search("q")
    assert excinfo.value.status_code == status
    assert excinfo.value.message == "nope"


def test_non_json_error_body_does_not_crash() -> None:
    def transport(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, bytes]:
        return 502, b"<html>bad gateway</html>"

    with pytest.raises(RootmemError) as excinfo:
        RootmemClient("http://h", "t", transport=transport).search("q")
    assert excinfo.value.status_code == 502


def test_base_url_must_be_http() -> None:
    with pytest.raises(ValueError):
        RootmemClient("ftp://h", "t")
