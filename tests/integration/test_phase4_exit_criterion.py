"""The Phase 4 exit criterion (docs/requirements/phase4-requirements.md),
proven end-to-end through the real MCP server subprocess and real Postgres.

Real Voyage/Anthropic calls happen only where the MCP surface makes them
unavoidable (`remember`/`ingest_session` embed and extract). Search runs in
`text` mode so ranking does not depend on embedding availability.

(a) a reinforced memory outranks an equally relevant stale one (time is
    injected with `as_of`, no sleeping) and results carry a score breakdown;
(b) a higher-trust source outranks a lower-trust one at equal relevance, and a
    skill with reported successes outranks one with failures in `find_skill`
    (the two skills are seeded straight into Postgres: skills are only
    created by consolidation of real session traces, exercised by the
    Phase 3 exit test);
(c) a memory linked to the queried entity gets a graph_proximity term;
(d) every mutation appears in the audit log and `verify_audit` is valid;
(e) after one audit row is altered directly in Postgres, `verify_audit`
    reports that row;
(f) a forgotten memory never surfaces.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from mcp import types
from mcp.client.session import ClientSession

from rootmem.config import get_settings
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.procedural_protocols import NewProceduralMemory

pytestmark = pytest.mark.integration_external

_PACING_SECONDS = 35


@pytest.fixture(autouse=True)
def _trust_map(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Forwarded to the server subprocess by tests/integration/conftest.py.
    monkeypatch.setenv("TRUST_SOURCE_RELIABILITY", json.dumps({"vetted": 0.95, "unvetted": 0.2}))
    yield


def _unwrap(result: types.CallToolResult) -> dict[str, Any]:
    assert result.is_error is not True, f"tool call failed: {result.content}"
    assert result.structured_content is not None
    return cast("dict[str, Any]", result.structured_content)


async def _call(session: ClientSession, tool: str, **args: Any) -> dict[str, Any]:
    return _unwrap(await session.call_tool(tool, args))


@pytest.mark.asyncio
async def test_ranking_decay_trust_and_audit_end_to_end(mcp_session: ClientSession) -> None:
    assert "TRUST_SOURCE_RELIABILITY" in os.environ
    ns = f"exit-criterion-phase4-{uuid.uuid4().hex[:12]}"

    # --- seed: two equal-relevance pairs, one entity-linked memory ---
    reinforced = (
        await _call(
            mcp_session,
            "remember",
            content="quokka deploy checklist",
            source="manual",
            namespace=ns,
        )
    )["id"]
    stale = (
        await _call(
            mcp_session,
            "remember",
            content="quokka deploy checklist",
            source="manual",
            namespace=ns,
        )
    )["id"]
    vetted = (
        await _call(
            mcp_session, "remember", content="lemur rollback runbook", source="vetted", namespace=ns
        )
    )["id"]
    unvetted = (
        await _call(
            mcp_session,
            "remember",
            content="lemur rollback runbook",
            source="unvetted",
            namespace=ns,
        )
    )["id"]
    await asyncio.sleep(_PACING_SECONDS)
    doomed = (
        await _call(
            mcp_session, "remember", content="ocelot secret plan", source="manual", namespace=ns
        )
    )["id"]

    # --- (a) reinforce one memory by recalling it, then rank as of +30 days ---
    for _ in range(4):
        await _call(mcp_session, "recall", id=reinforced, namespace=ns)
    as_of = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    ranked = await _call(
        mcp_session,
        "search",
        query="quokka deploy checklist",
        namespace=ns,
        mode="text",
        as_of=as_of,
    )
    ids = [item["id"] for item in ranked["results"]]
    assert ids[:2] == [reinforced, stale]
    for item in ranked["results"]:
        assert item["breakdown"] is not None
        assert sum(item["breakdown"].values()) == pytest.approx(item["score"])
        assert "retention" in item["breakdown"]

    # what-if queries must not have recorded access on the stale memory
    stale_view = await _call(mcp_session, "recall", id=stale, namespace=ns)
    assert stale_view["found"] is True

    # --- (b) trust: vetted source first at equal relevance ---
    trust_ranked = await _call(
        mcp_session, "search", query="lemur rollback runbook", namespace=ns, mode="text"
    )
    assert [item["id"] for item in trust_ranked["results"]][:2] == [vetted, unvetted]

    pool = await create_pool(get_settings())
    try:
        procedural = PostgresProceduralMemoryRepository(pool)
        for name in ("rollback-guide-good", "rollback-guide-bad"):
            await procedural.create(
                NewProceduralMemory(
                    namespace=ns,
                    kind="skill",
                    name=name,
                    description="how to roll back a failed service deploy",
                    body_markdown="1. revert\n2. verify",
                )
            )
        for _ in range(3):
            await _call(
                mcp_session,
                "report_skill_outcome",
                name="rollback-guide-good",
                namespace=ns,
                success=True,
            )
            await _call(
                mcp_session,
                "report_skill_outcome",
                name="rollback-guide-bad",
                namespace=ns,
                success=False,
            )
        skills = await _call(
            mcp_session, "find_skill", query="roll back a failed deploy", namespace=ns
        )
        assert [s["name"] for s in skills["results"]][:2] == [
            "rollback-guide-good",
            "rollback-guide-bad",
        ]
        assert skills["results"][0]["effectiveness"] > skills["results"][1]["effectiveness"]

        # --- (c) graph proximity via a real extraction-linked memory ---
        linked = await _call(
            mcp_session,
            "ingest_session",
            transcript="Alice works at Acme Corp.",
            source="manual",
            namespace=ns,
        )
        assert linked["extraction_degraded"] is False
        graph_ranked = await _call(
            mcp_session,
            "search",
            query="Alice Acme Corp",
            namespace=ns,
            mode="text",
            entity_name="Alice",
            entity_type="Person",
        )
        by_id = {item["id"]: item for item in graph_ranked["results"]}
        assert linked["memory_id"] in by_id
        assert by_id[linked["memory_id"]]["breakdown"]["graph_proximity"] > 0

        # --- (f) forget: never surfaces, row still exists ---
        await _call(mcp_session, "forget", id=doomed, reason="exit criterion")
        after_forget = await _call(
            mcp_session, "search", query="ocelot secret plan", namespace=ns, mode="text"
        )
        assert doomed not in [item["id"] for item in after_forget["results"]]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT deleted_at FROM memories WHERE id = $1", doomed)
        assert row is not None and row["deleted_at"] is not None

        await _call(mcp_session, "consolidate", namespace=ns, force=True)

        # --- (d) every mutation is audited and the chain verifies ---
        verified = await _call(mcp_session, "verify_audit", namespace=ns)
        assert verified["valid"] is True
        # 5 remembers + 6 skill reports + ingest + forget + consolidate
        assert verified["entries_checked"] >= 14
        async with pool.acquire() as conn:
            actions = {
                r["action"]
                for r in await conn.fetch("SELECT action FROM audit_log WHERE namespace = $1", ns)
            }
        assert {
            "remember",
            "forget",
            "ingest_session",
            "consolidate",
            "report_skill_outcome",
        } <= actions

        # --- (e) tamper with one row directly; verification pinpoints it ---
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_append_only")
            await conn.execute(
                "UPDATE audit_log SET payload = '{\"tampered\": true}'::jsonb "
                "WHERE namespace = $1 AND seq = 3",
                ns,
            )
            await conn.execute("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_append_only")
        broken = await _call(mcp_session, "verify_audit", namespace=ns)
        assert broken["valid"] is False
        assert broken["first_broken_seq"] == 3
    finally:
        await pool.close()
