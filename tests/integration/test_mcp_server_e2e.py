"""Launches the real MCP server as a subprocess over stdio and drives it
through the actual `mcp` client/session protocol layer — not the bare
Python tool functions (that's tests/unit/integration/test_mcp_tools_fake_backend.py)
and not the server's in-process `call_tool()` shortcut either. This is the
strongest signal short of a real Claude Code/Cursor session that stdio
transport, argument-schema flattening, and structured-output serialization
all work end-to-end against a real Postgres backend.

Requires Docker (`docker compose up -d`) and migrations applied. The
`mcp_session` fixture lives in tests/integration/conftest.py, shared with
test_phase1_exit_criterion.py.

Marked `integration_external`, not the default `integration` marker: since
Phase 1, the real server's `remember` always calls the live Voyage API to
embed content (ADR 0007) — every test here that calls `remember` now
transitively costs real money per run, exactly the condition NFR6 defines
as needing the separate, sparse job (see tests/conftest.py's collection
hook, which explicitly excludes `integration_external`-marked tests from
the plain `integration` marker for this reason).
"""

from __future__ import annotations

import pytest
from mcp import types
from mcp.client.session import ClientSession

pytestmark = pytest.mark.integration_external


@pytest.mark.asyncio
async def test_lists_all_nine_tools(mcp_session: ClientSession) -> None:
    result = await mcp_session.list_tools()
    names = {tool.name for tool in result.tools}
    assert names == {
        "remember",
        "recall",
        "update",
        "forget",
        "search",
        "related",
        "ingest_session",
        "consolidate",
        "feedback",
    }


@pytest.mark.asyncio
async def test_remember_then_recall_round_trip(mcp_session: ClientSession) -> None:
    remember_result = await mcp_session.call_tool(
        "remember", {"content": "e2e round-trip fact", "source": "e2e-test"}
    )
    assert isinstance(remember_result, types.CallToolResult)
    assert remember_result.is_error is not True
    assert remember_result.structured_content is not None
    memory_id = remember_result.structured_content["id"]

    recall_result = await mcp_session.call_tool("recall", {"id": memory_id})
    assert isinstance(recall_result, types.CallToolResult)
    assert recall_result.is_error is not True
    assert recall_result.structured_content is not None
    assert recall_result.structured_content["found"] is True
    assert recall_result.structured_content["record"]["content"] == "e2e round-trip fact"


@pytest.mark.asyncio
async def test_forget_then_recall_reports_not_found(mcp_session: ClientSession) -> None:
    remember_result = await mcp_session.call_tool(
        "remember", {"content": "e2e forget-me fact", "source": "e2e-test"}
    )
    assert remember_result.structured_content is not None
    memory_id = remember_result.structured_content["id"]

    await mcp_session.call_tool("forget", {"id": memory_id})
    recall_result = await mcp_session.call_tool("recall", {"id": memory_id})

    assert recall_result.structured_content is not None
    assert recall_result.structured_content["found"] is False


@pytest.mark.asyncio
async def test_blank_content_surfaces_as_clean_tool_error(mcp_session: ClientSession) -> None:
    result = await mcp_session.call_tool("remember", {"content": "   ", "source": "e2e-test"})

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    assert "blank" in str(result.content).lower()


@pytest.mark.asyncio
async def test_ingest_session_then_related_round_trip(mcp_session: ClientSession) -> None:
    """The real end-to-end path for the two new Phase 1 tools: a transcript
    goes in via `ingest_session` (real embedding + real extraction), and
    `related` reads back what the extraction pipeline wrote to the graph."""
    ingest_result = await mcp_session.call_tool(
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

    related_result = await mcp_session.call_tool(
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


@pytest.mark.asyncio
async def test_feedback_confirmed_raises_relation_confidence_round_trip(
    mcp_session: ClientSession,
) -> None:
    """The real end-to-end path for Phase 2's new `feedback` tool: an
    extracted relation's confidence measurably increases as a direct,
    observable result of an explicit `confirmed` report."""
    ingest_result = await mcp_session.call_tool(
        "ingest_session",
        {
            "transcript": "E2eFeedbackPerson works at E2eFeedbackOrg.",
            "source": "e2e-test",
            "namespace": "e2e-feedback-test",
        },
    )
    assert isinstance(ingest_result, types.CallToolResult)
    assert ingest_result.is_error is not True

    related_result = await mcp_session.call_tool(
        "related",
        {
            "entity_name": "E2eFeedbackPerson",
            "entity_type": "Person",
            "namespace": "e2e-feedback-test",
        },
    )
    assert related_result.structured_content is not None
    relations = related_result.structured_content["relations"]
    assert len(relations) >= 1
    relation_id = relations[0]["id"]
    original_confidence = relations[0]["confidence"]

    feedback_result = await mcp_session.call_tool(
        "feedback",
        {
            "relation_id": relation_id,
            "namespace": "e2e-feedback-test",
            "outcome": "confirmed",
            "confidence": 1.0,
        },
    )
    assert isinstance(feedback_result, types.CallToolResult)
    assert feedback_result.is_error is not True
    assert feedback_result.structured_content is not None
    assert feedback_result.structured_content["relation"]["confidence"] > original_confidence


@pytest.mark.asyncio
async def test_consolidate_force_runs_without_error(mcp_session: ClientSession) -> None:
    result = await mcp_session.call_tool(
        "consolidate", {"namespace": "e2e-consolidate-test", "force": True}
    )

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is not True
    assert result.structured_content is not None
    assert result.structured_content["ran"] is True
    assert result.structured_content["trigger_reason"] == "manual"
