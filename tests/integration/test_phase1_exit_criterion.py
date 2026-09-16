"""The Phase 1 exit criterion (docs/requirements/phase1-requirements.md),
proven end-to-end via the real MCP server subprocess, real Postgres, real
Voyage embeddings, and real Anthropic extraction — no fakes anywhere in
this test.

Scenario: two session transcripts go in via `ingest_session`, the second
contradicting the first (same entity, same predicate, different object).
The system must, via MCP alone:

(a) extract entities and relations into the graph, each linked back to its
    source memory row;
(b) detect the contradiction and resolve it — the old relation superseded,
    never deleted or overwritten;
(c) answer a semantic-only query (zero lexical overlap with the stored
    sentence) that full-text search cannot — proving the vector component
    does real work, not riding lexical coincidence. This is deliberately
    tested with an *independent* fact, not the contradiction pair itself:
    a real run surfaced that Phase 1's `search` ranks by pure content
    similarity with no awareness of the graph's supersession state (that
    connection is explicitly Phase 4's ranking-formula scope, not built
    yet) — asserting "the current fact outranks the superseded one" would
    test something this phase never wired up. `related` (d) is what
    actually proves current-vs-superseded state is tracked correctly.
(d) a `related` call against the entity returns both the current and
    superseded relations with correct valid_from/valid_to.

Marked `integration_external` (real Voyage + Anthropic calls, real money
per run, NFR6) — this is the single most expensive test in the suite and
the literal automated sign-off gate for tagging `v0.1.0-phase1`.

Paced deliberately: this account's Voyage tier (no payment method on file)
is hard-capped at 3 requests/minute — a real 429 from actually running this
test surfaced it (see VoyageEmbeddingProvider's max_retries). The test
needs 4 embedding calls (2 ingests for the contradiction, 1 ingest for the
independent fact, 1 query embed), so there's a deliberate pause between the
contradiction phase and the independent-fact phase to keep any 60-second
window under 3 calls, rather than relying on retry backoff to paper over a
hard quota.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import pytest
from mcp import types
from mcp.client.session import ClientSession

pytestmark = pytest.mark.integration_external

_RATE_LIMIT_PACING_SECONDS = 35


def _unwrap(result: types.CallToolResult) -> dict[str, Any]:
    """Structured tool output is loosely-typed JSON on the wire — `Any` is
    the honest type here, not `object`, since every field access below
    narrows it manually via the assertions that follow. The explicit cast
    (rather than a bare return) is what it takes to satisfy
    `--warn-return-any`: the SDK's own field is typed as `Any | None`, and
    mypy flags returning a raw `Any` value regardless of the declared
    signature."""
    assert result.is_error is not True, f"tool call failed: {result.content}"
    assert result.structured_content is not None
    return cast("dict[str, Any]", result.structured_content)


@pytest.mark.asyncio
async def test_contradiction_extraction_and_graph_history_end_to_end(
    mcp_session: ClientSession,
) -> None:
    """Proves (a), (b), and (d) — extraction, contradiction resolution, and
    correct bi-temporal graph history — via `ingest_session` and `related`."""
    namespace = f"exit-criterion-{uuid.uuid4().hex[:12]}"

    first_ingest = _unwrap(
        await mcp_session.call_tool(
            "ingest_session",
            {
                "transcript": "Alice works at Acme Corp.",
                "source": "exit-criterion-test",
                "namespace": namespace,
            },
        )
    )
    assert first_ingest["relations_extracted"] >= 1
    assert first_ingest["extraction_degraded"] is False

    second_ingest = _unwrap(
        await mcp_session.call_tool(
            "ingest_session",
            {
                "transcript": "Alice joined Globex as an engineer.",
                "source": "exit-criterion-test",
                "namespace": namespace,
            },
        )
    )
    assert second_ingest["relations_extracted"] >= 1
    assert second_ingest["extraction_degraded"] is False
    # (b): the actual contradiction-detection proof — the second ingest's
    # relation superseded the first's, rather than sitting alongside it
    # unresolved or being silently dropped.
    assert second_ingest["superseded_count"] == 1
    assert second_ingest["contested_count"] == 0

    # (d): related returns both relations, correct bi-temporal history —
    # this is the actual proof that "current" vs "superseded" is tracked
    # correctly, since search (tested separately below) doesn't know this.
    related = _unwrap(
        await mcp_session.call_tool(
            "related",
            {"entity_name": "Alice", "entity_type": "Person", "namespace": namespace},
        )
    )
    assert related["entity_found"] is True
    relations = related["relations"]
    assert isinstance(relations, list)
    assert len(relations) == 2

    active = [r for r in relations if r["is_active"]]
    superseded = [r for r in relations if not r["is_active"]]
    assert len(active) == 1
    assert len(superseded) == 1
    assert active[0]["valid_to"] is None
    assert superseded[0]["valid_to"] is not None
    assert active[0]["supersedes"] == superseded[0]["id"]
    assert superseded[0]["superseded_by"] == active[0]["id"]

    # Deliberate pause before the next phase's embedding calls — see the
    # module docstring's rate-limit note. This test's two ingests above
    # already used 2 of this account's 3-per-minute Voyage budget.
    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # (c): an independent fact (not part of the contradiction pair, so
    # there's no ambiguity about which of two related facts should rank
    # first — that's not what this phase's search can promise) and a query
    # with zero lexical overlap with it.
    await mcp_session.call_tool(
        "ingest_session",
        {
            "transcript": "The engineering team relocated to a new office at 500 Market Street.",
            "source": "exit-criterion-test",
            "namespace": namespace,
        },
    )

    query = "what is the new address"

    text_only = _unwrap(
        await mcp_session.call_tool(
            "search", {"query": query, "namespace": namespace, "mode": "text"}
        )
    )
    text_only_contents = [r["content"] for r in text_only["results"]]
    market_street_in_text_results = any("Market Street" in c for c in text_only_contents)

    semantic = _unwrap(
        await mcp_session.call_tool(
            "search", {"query": query, "namespace": namespace, "mode": "semantic"}
        )
    )
    semantic_results = semantic["results"]
    assert isinstance(semantic_results, list)
    assert len(semantic_results) >= 1
    assert any("Market Street" in r["content"] for r in semantic_results)

    # The actual proof: semantic search finds the lexically-disjoint fact;
    # full-text search, with zero shared vocabulary, does not — demonstrating
    # the vector component does real work rather than riding lexical
    # coincidence.
    assert not market_street_in_text_results
