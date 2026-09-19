"""Authorization inside `build_server` (ADR 0029/0030): namespace ownership,
fail-closed authentication, and per-identity audit attribution, against the
in-memory fakes and the SDK's own auth context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from rootmem.config import Settings
from rootmem.consolidation.fakes.scripted_distillation_provider import ScriptedDistillationProvider
from rootmem.consolidation.fakes.scripted_procedural_distillation_provider import (
    ScriptedProceduralDistillationProvider,
)
from rootmem.embedding.fakes.fixture_provider import FixtureReplayEmbeddingProvider
from rootmem.extraction.fakes.scripted_provider import ScriptedExtractionProvider
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.identity.verifier import RootmemTokenVerifier
from rootmem.integration.mcp.server import build_server
from rootmem.storage.fakes.in_memory_audit_repository import InMemoryAuditLogRepository
from rootmem.storage.fakes.in_memory_consolidation_repository import InMemoryConsolidationRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_identity_repository import InMemoryIdentityRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository


class _Rig:
    def __init__(self, *, authenticated: bool) -> None:
        self.memories = InMemoryMemoryRepository()
        self.audit = InMemoryAuditLogRepository()
        self.identities = InMemoryIdentityRepository()
        verifier = RootmemTokenVerifier(self.identities) if authenticated else None
        auth = None
        if authenticated:
            from mcp.server.auth.settings import AuthSettings

            auth = AuthSettings(
                issuer_url="http://127.0.0.1:1",
                resource_server_url="http://127.0.0.1:1",
                validate_token_resource=False,
            )
        self.server: MCPServer = build_server(
            self.memories,
            InMemoryGraphRepository(),
            FixtureReplayEmbeddingProvider(),
            ScriptedExtractionProvider(),
            InMemoryConsolidationRepository(),
            ScriptedDistillationProvider(),
            InMemoryProceduralMemoryRepository(),
            ScriptedProceduralDistillationProvider(),
            Settings(),
            self.audit,
            verifier,
            auth,
        )

    async def issue(self, name: str, namespaces: list[str]) -> AccessToken:
        token = generate_token()
        await self.identities.create(name, namespaces, hash_token(token))
        verifier = RootmemTokenVerifier(self.identities)
        access = await verifier.verify_token(token)
        assert access is not None
        return access

    async def call(self, tool: str, **args: Any) -> Any:
        return await self.server.call_tool(tool, args)


@contextmanager
def _as(access: AccessToken | None) -> Iterator[None]:
    reset = auth_context_var.set(AuthenticatedUser(access) if access is not None else None)
    try:
        yield
    finally:
        auth_context_var.reset(reset)


async def test_owner_can_write_and_read_own_namespace() -> None:
    rig = _Rig(authenticated=True)
    alice = await rig.issue("alice", ["ns-a"])
    with _as(alice):
        await rig.call("remember", content="alice fact", source="t", namespace="ns-a")
        found = await rig.call("search", query="alice", namespace="ns-a", mode="text")
    assert "alice fact" in str(found)


async def test_other_identity_is_denied_every_namespaced_tool_without_side_effects() -> None:
    rig = _Rig(authenticated=True)
    alice = await rig.issue("alice", ["ns-a"])
    bob = await rig.issue("bob", ["ns-b"])
    with _as(alice):
        remembered = await rig.call("remember", content="secret", source="t", namespace="ns-a")
    memory_id = str(remembered.structured_content["id"])
    entries_before = len(await rig.audit.list_entries("ns-a"))

    with _as(bob):
        for tool, args in (
            ("recall", {"id": memory_id, "namespace": "ns-a"}),
            ("search", {"query": "secret", "namespace": "ns-a"}),
            ("remember", {"content": "x", "source": "t", "namespace": "ns-a"}),
            ("verify_audit", {"namespace": "ns-a"}),
            ("consolidate", {"namespace": "ns-a", "force": True}),
            ("find_skill", {"query": "q", "namespace": "ns-a"}),
        ):
            with pytest.raises(ToolError):
                await rig.call(tool, **args)
        for tool, args in (
            ("update", {"id": memory_id, "content": "hijacked"}),
            ("forget", {"id": memory_id}),
        ):
            with pytest.raises(ToolError, match="not found"):
                await rig.call(tool, **args)

    record = await rig.memories.get_by_id("ns-a", memory_id)
    assert record is not None and record.content == "secret"
    assert len(await rig.audit.list_entries("ns-a")) == entries_before


async def test_unknown_memory_and_foreign_memory_answer_alike() -> None:
    rig = _Rig(authenticated=True)
    alice = await rig.issue("alice", ["ns-a"])
    bob = await rig.issue("bob", ["ns-b"])
    with _as(alice):
        remembered = await rig.call("remember", content="secret", source="t", namespace="ns-a")
    real_id = str(remembered.structured_content["id"])
    with _as(bob):
        with pytest.raises(ToolError) as foreign:
            await rig.call("forget", id=real_id)
        with pytest.raises(ToolError) as missing:
            await rig.call("forget", id="00000000-0000-0000-0000-000000000000")
    assert "not found" in str(foreign.value) and "not found" in str(missing.value)


async def test_calls_without_an_identity_fail_closed_when_auth_is_required() -> None:
    rig = _Rig(authenticated=True)
    with _as(None):
        with pytest.raises(ToolError, match="authentication required"):
            await rig.call("recall", id="x", namespace="ns-a")
        with pytest.raises(ToolError, match="authentication required"):
            await rig.call("search", query="q", namespace="ns-a")


async def test_audit_actor_is_the_authenticated_identity() -> None:
    rig = _Rig(authenticated=True)
    alice = await rig.issue("alice", ["ns-a"])
    with _as(alice):
        await rig.call("remember", content="attributed", source="t", namespace="ns-a")
        verified = await rig.call("verify_audit", namespace="ns-a")
    entries = await rig.audit.list_entries("ns-a")
    assert [e.actor for e in entries] == ["alice"]
    assert verified.structured_content["valid"] is True


async def test_stdio_mode_is_unchanged_local_caller_owns_everything() -> None:
    rig = _Rig(authenticated=False)
    with _as(None):
        await rig.call("remember", content="local fact", source="t", namespace="any-ns")
        found = await rig.call("search", query="local", namespace="any-ns", mode="text")
    assert "local fact" in str(found)
    entries = await rig.audit.list_entries("any-ns")
    assert entries[0].actor == Settings().audit_actor


async def test_tool_schemas_survive_the_guard_decorator() -> None:
    rig = _Rig(authenticated=False)
    tools = {t.name: t for t in await rig.server.list_tools()}
    assert len(tools) == 13
    search_props = tools["search"].input_schema["properties"]
    assert {"query", "namespace", "entity_name", "entity_type", "as_of"} <= set(search_props)
    assert "id" in tools["forget"].input_schema["properties"]


async def test_revoked_identity_fails_verification() -> None:
    rig = _Rig(authenticated=True)
    token = generate_token()
    await rig.identities.create("carol", ["ns-c"], hash_token(token))
    verifier = RootmemTokenVerifier(rig.identities)
    assert await verifier.verify_token(token) is not None
    await rig.identities.revoke("carol")
    assert await verifier.verify_token(token) is None
    assert await verifier.verify_token("rmk_not-a-real-token") is None
