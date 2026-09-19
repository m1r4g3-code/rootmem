"""Scopes, rate limiting and the health route inside `build_server`
(ADR 0034/0035), against the in-memory fakes."""

from __future__ import annotations

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from starlette.testclient import TestClient

from rootmem.identity.ratelimit import TokenBucketLimiter
from tests.unit.identity.test_server_authorization import _as, _Rig


async def test_read_identity_can_read_but_no_write_tool_runs() -> None:
    rig = _Rig(authenticated=True)
    writer = await rig.issue("writer", ["ns-a"])
    reader = await rig.issue("reader", ["ns-a"], scope="read")
    with _as(writer):
        made = await rig.call("remember", content="shared fact", source="t", namespace="ns-a")
    memory_id = str(made.structured_content["id"])
    entries_before = len(await rig.audit.list_entries("ns-a"))

    with _as(reader):
        found = await rig.call("search", query="shared", namespace="ns-a", mode="text")
        assert "shared fact" in str(found)
        await rig.call("recall", id=memory_id, namespace="ns-a")
        assert (await rig.call("verify_audit", namespace="ns-a")).structured_content["valid"]
        for tool, args in (
            ("remember", {"content": "x", "source": "t", "namespace": "ns-a"}),
            ("update", {"id": memory_id, "content": "changed"}),
            ("forget", {"id": memory_id}),
            ("consolidate", {"namespace": "ns-a", "force": True}),
            ("feedback", {"relation_id": "r", "outcome": "confirmed", "namespace": "ns-a"}),
            ("report_skill_outcome", {"name": "s", "success": True, "namespace": "ns-a"}),
            ("ingest_session", {"transcript": "t", "source": "t", "namespace": "ns-a"}),
        ):
            with pytest.raises(ToolError, match="scope 'read'"):
                await rig.call(tool, **args)

    record = await rig.memories.get_by_id("ns-a", memory_id)
    assert record is not None and record.content == "shared fact"
    assert len(await rig.audit.list_entries("ns-a")) == entries_before


async def test_rate_limit_throttles_one_identity_not_another() -> None:
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=2, clock=lambda: 0.0)
    rig = _Rig(authenticated=True, rate_limiter=limiter)
    busy = await rig.issue("busy", ["ns-a"])
    calm = await rig.issue("calm", ["ns-b"])

    with _as(busy):
        await rig.call("search", query="q", namespace="ns-a", mode="text")
        await rig.call("search", query="q", namespace="ns-a", mode="text")
        with pytest.raises(ToolError, match="rate limit exceeded"):
            await rig.call("search", query="q", namespace="ns-a", mode="text")
    with _as(calm):
        await rig.call("search", query="q", namespace="ns-b", mode="text")


async def test_throttled_write_has_no_side_effects() -> None:
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=lambda: 0.0)
    rig = _Rig(authenticated=True, rate_limiter=limiter)
    agent = await rig.issue("agent", ["ns-a"])
    with _as(agent):
        await rig.call("remember", content="first", source="t", namespace="ns-a")
        with pytest.raises(ToolError, match="rate limit"):
            await rig.call("remember", content="second", source="t", namespace="ns-a")
    assert len(await rig.audit.list_entries("ns-a")) == 1


async def test_local_stdio_caller_is_never_rate_limited() -> None:
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=1, clock=lambda: 0.0)
    rig = _Rig(authenticated=False, rate_limiter=limiter)
    with _as(None):
        for _ in range(5):
            await rig.call("search", query="q", namespace="any", mode="text")


def test_healthz_is_unauthenticated_and_reveals_only_status() -> None:
    async def healthy() -> bool:
        return True

    rig = _Rig(authenticated=True, health_check=healthy)
    with TestClient(rig.server.streamable_http_app()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_reports_503_when_the_check_fails_or_raises() -> None:
    async def down() -> bool:
        return False

    async def boom() -> bool:
        raise RuntimeError("database password is hunter2")

    for check in (down, boom):
        rig = _Rig(authenticated=True, health_check=check)
        with TestClient(rig.server.streamable_http_app()) as client:
            response = client.get("/healthz")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert "hunter2" not in response.text
