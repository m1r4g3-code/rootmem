"""Launches the real MCP server as a subprocess over stdio and drives it
through the actual `mcp` client/session protocol layer — not the bare
Python tool functions (that's tests/unit/integration/test_mcp_tools_fake_backend.py)
and not the server's in-process `call_tool()` shortcut either. This is the
strongest signal short of a real Claude Code/Cursor session that stdio
transport, argument-schema flattening, and structured-output serialization
all work end-to-end against a real Postgres backend.

Requires Docker (`docker compose up -d`) and migrations applied.

Marked `integration_external`, not the default `integration` marker: since
Phase 1, the real server's `remember` always calls the live Voyage API to
embed content (ADR 0007) — every test here that calls `remember` now
transitively costs real money per run, exactly the condition NFR6 defines
as needing the separate, sparse job (see tests/conftest.py's collection
hook, which explicitly excludes `integration_external`-marked tests from
the plain `integration` marker for this reason).
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

pytestmark = pytest.mark.integration_external

_ENV_VARS_TO_FORWARD = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_SSLMODE",
    "ROOTMEM_LOG_LEVEL",
    # Phase 1: the real server now constructs VoyageEmbeddingProvider and
    # AnthropicExtractionProvider at startup (ADR 0009), which fail fast
    # without these — the subprocess needs them forwarded too.
    "VOYAGE_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[ClientSession]:
    server_env = {name: os.environ[name] for name in _ENV_VARS_TO_FORWARD if name in os.environ}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rootmem.integration.mcp.server"],
        env=server_env,
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client_session:
                await client_session.initialize()
                yield client_session
    except RuntimeError as exc:
        # Known Windows-specific anyio/mcp SDK teardown quirk: closing the
        # subprocess's stdio pipes can raise "Attempted to exit cancel scope
        # in a different task than it was entered in" from stdio_client's
        # own __aexit__, strictly during cleanup, after the test body (and
        # its assertions) have already completed successfully. Suppress
        # only this specific message so a real failure still surfaces.
        if "cancel scope" not in str(exc):
            raise


@pytest.mark.asyncio
async def test_lists_all_seven_tools(session: ClientSession) -> None:
    result = await session.list_tools()
    names = {tool.name for tool in result.tools}
    assert names == {
        "remember",
        "recall",
        "update",
        "forget",
        "search",
        "related",
        "ingest_session",
    }


@pytest.mark.asyncio
async def test_remember_then_recall_round_trip(session: ClientSession) -> None:
    remember_result = await session.call_tool(
        "remember", {"content": "e2e round-trip fact", "source": "e2e-test"}
    )
    assert isinstance(remember_result, types.CallToolResult)
    assert remember_result.is_error is not True
    assert remember_result.structured_content is not None
    memory_id = remember_result.structured_content["id"]

    recall_result = await session.call_tool("recall", {"id": memory_id})
    assert isinstance(recall_result, types.CallToolResult)
    assert recall_result.is_error is not True
    assert recall_result.structured_content is not None
    assert recall_result.structured_content["found"] is True
    assert recall_result.structured_content["record"]["content"] == "e2e round-trip fact"


@pytest.mark.asyncio
async def test_forget_then_recall_reports_not_found(session: ClientSession) -> None:
    remember_result = await session.call_tool(
        "remember", {"content": "e2e forget-me fact", "source": "e2e-test"}
    )
    assert remember_result.structured_content is not None
    memory_id = remember_result.structured_content["id"]

    await session.call_tool("forget", {"id": memory_id})
    recall_result = await session.call_tool("recall", {"id": memory_id})

    assert recall_result.structured_content is not None
    assert recall_result.structured_content["found"] is False


@pytest.mark.asyncio
async def test_blank_content_surfaces_as_clean_tool_error(session: ClientSession) -> None:
    result = await session.call_tool("remember", {"content": "   ", "source": "e2e-test"})

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    assert "blank" in str(result.content).lower()


@pytest.mark.asyncio
async def test_ingest_session_then_related_round_trip(session: ClientSession) -> None:
    """The real end-to-end path for the two new Phase 1 tools: a transcript
    goes in via `ingest_session` (real embedding + real extraction), and
    `related` reads back what the extraction pipeline wrote to the graph."""
    ingest_result = await session.call_tool(
        "ingest_session",
        {
            "transcript": "E2eProbePerson works at E2eProbeOrg.",
            "source": "e2e-test",
            "namespace": "e2e-ingest-test",
        },
    )
    assert isinstance(ingest_result, types.CallToolResult)
    assert ingest_result.is_error is not True
    assert ingest_result.structured_content is not None
    assert ingest_result.structured_content["relations_extracted"] >= 1
    assert ingest_result.structured_content["extraction_degraded"] is False

    related_result = await session.call_tool(
        "related",
        {
            "entity_name": "E2eProbePerson",
            "entity_type": "Person",
            "namespace": "e2e-ingest-test",
        },
    )
    assert isinstance(related_result, types.CallToolResult)
    assert related_result.is_error is not True
    assert related_result.structured_content is not None
    assert related_result.structured_content["entity_found"] is True
    assert len(related_result.structured_content["relations"]) >= 1
