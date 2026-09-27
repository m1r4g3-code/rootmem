"""The REST facade (ADR 0036) shares the MCP tool path, so its behavior must
match MCP's exactly; these tests pin that with Starlette's test client."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from starlette.testclient import TestClient

from rootmem.identity.ratelimit import TokenBucketLimiter
from tests.unit.identity.test_server_authorization import _as, _Rig


@contextmanager
def _client(rig: _Rig) -> Iterator[TestClient]:
    with TestClient(rig.server.streamable_http_app()) as client:
        yield client


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_malformed_and_unknown_tokens_are_401() -> None:
    rig = _Rig(authenticated=True)
    with _client(rig) as client:
        assert client.get("/v1/tools").status_code == 401
        assert client.post("/v1/tools/search", json={"query": "q"}).status_code == 401
        for header in ("Bearer", "Basic abc", "Bearer rmk_unknown", ""):
            response = client.post(
                "/v1/tools/search", json={"query": "q"}, headers={"Authorization": header}
            )
            assert response.status_code == 401, header
        assert client.get("/v1/tools").headers["www-authenticate"] == "Bearer"


async def test_lists_all_fourteen_tools_with_schemas() -> None:
    rig = _Rig(authenticated=True)
    agent = await rig.issue("agent", ["ns-a"])
    with _client(rig) as client:
        response = client.get("/v1/tools", headers=_auth(agent.token))
    assert response.status_code == 200
    tools = {t["name"]: t for t in response.json()}
    assert len(tools) == 14  # Phase 8 added `ruminate`
    assert "query" in tools["search"]["input_schema"]["properties"]


async def test_write_then_read_matches_the_mcp_path() -> None:
    rig = _Rig(authenticated=True)
    agent = await rig.issue("agent", ["ns-a"])
    with _client(rig) as client:
        made = client.post(
            "/v1/tools/remember",
            json={"content": "rest fact", "source": "t", "namespace": "ns-a"},
            headers=_auth(agent.token),
        )
        assert made.status_code == 200
        memory_id = made.json()["result"]["id"]

        via_rest = client.post(
            "/v1/tools/search",
            json={"query": "rest", "namespace": "ns-a", "mode": "text"},
            headers=_auth(agent.token),
        ).json()["result"]

    with _as(agent):
        via_mcp = (
            await rig.call("search", query="rest", namespace="ns-a", mode="text")
        ).structured_content
    assert via_mcp is not None
    assert [r["id"] for r in via_rest["results"]] == [r["id"] for r in via_mcp["results"]]
    assert via_rest["results"][0]["id"] == memory_id
    # The write was audited under the authenticated identity, exactly as over MCP.
    assert [e.actor for e in await rig.audit.list_entries("ns-a")] == ["agent"]


async def test_foreign_namespace_is_403_and_changes_nothing() -> None:
    rig = _Rig(authenticated=True)
    alice = await rig.issue("alice", ["ns-a"])
    bob = await rig.issue("bob", ["ns-b"])
    with _client(rig) as client:
        made = client.post(
            "/v1/tools/remember",
            json={"content": "secret", "source": "t", "namespace": "ns-a"},
            headers=_auth(alice.token),
        )
        memory_id = made.json()["result"]["id"]
        for tool, body in (
            ("search", {"query": "secret", "namespace": "ns-a"}),
            ("remember", {"content": "x", "source": "t", "namespace": "ns-a"}),
            ("verify_audit", {"namespace": "ns-a"}),
        ):
            response = client.post(f"/v1/tools/{tool}", json=body, headers=_auth(bob.token))
            assert response.status_code == 403, tool
        for tool in ("update", "forget"):
            body = {"id": memory_id, "content": "x"} if tool == "update" else {"id": memory_id}
            response = client.post(f"/v1/tools/{tool}", json=body, headers=_auth(bob.token))
            assert response.status_code == 404, tool  # indistinguishable from missing
    assert len(await rig.audit.list_entries("ns-a")) == 1


async def test_read_scope_gets_403_on_write_tools_and_200_on_read_tools() -> None:
    rig = _Rig(authenticated=True)
    reader = await rig.issue("reader", ["ns-a"], scope="read")
    with _client(rig) as client:
        ok = client.post(
            "/v1/tools/search",
            json={"query": "q", "namespace": "ns-a", "mode": "text"},
            headers=_auth(reader.token),
        )
        denied = client.post(
            "/v1/tools/remember",
            json={"content": "x", "source": "t", "namespace": "ns-a"},
            headers=_auth(reader.token),
        )
    assert ok.status_code == 200
    assert denied.status_code == 403
    assert "scope" in denied.json()["error"]


async def test_bad_requests_map_to_404_and_422() -> None:
    rig = _Rig(authenticated=True)
    agent = await rig.issue("agent", ["ns-a"])
    headers = _auth(agent.token)
    with _client(rig) as client:
        assert client.post("/v1/tools/nope", json={}, headers=headers).status_code == 404
        assert (
            client.post("/v1/tools/remember", content=b"{not json", headers=headers).status_code
            == 422
        )
        assert client.post("/v1/tools/remember", json=[1, 2], headers=headers).status_code == 422
        blank = client.post(
            "/v1/tools/remember",
            json={"content": "  ", "source": "t", "namespace": "ns-a"},
            headers=headers,
        )
        assert blank.status_code == 422
        missing = client.post("/v1/tools/remember", json={"namespace": "ns-a"}, headers=headers)
        assert missing.status_code == 422


async def test_rate_limit_is_429_over_rest() -> None:
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=lambda: 0.0)
    rig = _Rig(authenticated=True, rate_limiter=limiter)
    agent = await rig.issue("agent", ["ns-a"])
    body = {"query": "q", "namespace": "ns-a", "mode": "text"}
    with _client(rig) as client:
        first = client.post("/v1/tools/search", json=body, headers=_auth(agent.token))
        second = client.post("/v1/tools/search", json=body, headers=_auth(agent.token))
    assert first.status_code == 200
    assert second.status_code == 429


async def test_revoked_token_stops_working_on_the_next_rest_call() -> None:
    rig = _Rig(authenticated=True)
    agent = await rig.issue("agent", ["ns-a"])
    body = {"query": "q", "namespace": "ns-a", "mode": "text"}
    with _client(rig) as client:
        assert (
            client.post("/v1/tools/search", json=body, headers=_auth(agent.token)).status_code
            == 200
        )
        await rig.identities.revoke("agent")
        assert (
            client.post("/v1/tools/search", json=body, headers=_auth(agent.token)).status_code
            == 401
        )
