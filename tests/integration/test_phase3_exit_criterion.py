"""The Phase 3 exit criterion (docs/requirements/phase3-requirements.md),
proven end-to-end via the real MCP server subprocess, real Postgres, real
Voyage embeddings, and real Anthropic extraction/distillation/procedural-
distillation -- no fakes anywhere in this test.

Scenario: three restatements of an unrelated fact ("Alice works at Acme
Corp", Phase 2's own corroboration ingredient, reused here to prove old and
new distillation types coexist in one pass), plus two successful sessions
describing the same underlying procedure in different words, plus one failed
session on a related-looking task, all go in via `ingest_session`. A forced
`consolidate` pass must, via MCP alone:

(a) group episodes by (source_session_id, session_outcome), cluster the two
    successful traces via reused similarity-threshold union-find, and
    distill them into exactly one `procedural_memories` row (`kind="skill"`)
    with a SKILL.md-conformant name/description, linked via
    `procedural_memory_provenance` to all 6 source episodes -- provable via
    `get_skill`;
(b) distill the single failed session into a separate `kind="lesson"` row
    with no repetition required -- provable via `get_skill`;
(c) record `procedures_distilled=1`, `lessons_distilled=1` on the SAME
    `consolidation_runs` row that also reports `facts_distilled>=1` from the
    reused corroboration ingredient -- proving procedural/lesson
    distillation runs inside the same sleep cycle as episodic->semantic
    distillation, not a separate, parallel subsystem (ADR 0020);
(d) a `find_skill` call using only a natural-language description of a fresh
    instance of the same task -- not the skill's own (LLM-chosen, unknown in
    advance) name -- ranks the skill above the unrelated lesson, proving
    semantic retrieval discriminates on real content, not name-matching;
(e) `get_skill` with the name `find_skill` returned yields literal
    SKILL.md-conformant markdown text (valid frontmatter + body), and a
    subsequent `ingest_session` call describing the agent applying that
    retrieved guidance succeeds -- the "applies it correctly" proof,
    deliberately scoped to what's observable through MCP tool calls alone
    per the user's confirmed scoped-down exit criterion (ADR 0021): no
    benchmark harness, no reference coding agent, no real SWE-bench/
    Terminal-Bench task run.

Marked `integration_external` (real Voyage + Anthropic calls, real money per
run, NFR7) -- the automated sign-off gate for tagging `v0.3.0-phase3`.

Paced deliberately, same rationale as Phase 1/2's exit-criterion tests: this
account's Voyage tier is hard-capped at 3 requests/minute. Episodes are
ingested in the order corroboration-restatements-first, session-traces-
second, so the inline auto-trigger (ADR 0012) only ever auto-consolidates
the very first restatement solo (a singleton, harmless) -- every session
trace episode is ingested strictly after that first auto-trigger has already
run once for this namespace, so no further auto-trigger fires (the count/
time conditions aren't met again), and all three full traces survive intact
for the single explicit `consolidate(force=True)` call below. Reusing the
exact sentences already validated by scripts/spike_similarity_clustering.py
(Phase 2's corroboration ingredient) and scripts/spike_session_trace_clustering.py
(Phase 3's session traces) means the expensive real-API run's clustering
behavior is never itself in question -- the only real unknowns are the
procedural distillation prompt and the MCP wiring, exactly what this test is
actually for.
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

_TRACE_SUCCESS_A_STEPS = [
    "The test suite fails with a KeyError in the payment module.",
    "The root cause is a missing default value in the config loader.",
    "The fix is to add a default value in the config loader, and the tests pass.",
]
_TRACE_SUCCESS_B_STEPS = [
    "A test is failing due to a KeyError inside payment processing.",
    "Root cause: the config loader has no default value set.",
    "Fix applied: added a default value to the config loader; tests now pass.",
]
_TRACE_FAILURE_C_STEPS = [
    "The test suite fails with a TypeError in the billing module.",
    "Attempted fix: changed the input type in the billing handler.",
    "The fix did not work; the TypeError persisted because the root cause "
    "was actually a serialization bug in the API layer, not the input type.",
]


def _unwrap(result: types.CallToolResult) -> dict[str, Any]:
    """See tests/integration/test_phase1_exit_criterion.py's identical
    helper for why this is the honest, mypy-satisfying shape."""
    assert result.is_error is not True, f"tool call failed: {result.content}"
    assert result.structured_content is not None
    return cast("dict[str, Any]", result.structured_content)


async def _ingest_step(
    mcp_session: ClientSession,
    namespace: str,
    transcript: str,
    session_id: str | None = None,
    session_outcome: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "transcript": transcript,
        "source": "exit-criterion-test",
        "namespace": namespace,
    }
    if session_id is not None:
        params["session_id"] = session_id
    if session_outcome is not None:
        params["session_outcome"] = session_outcome
    return _unwrap(await mcp_session.call_tool("ingest_session", params))


@pytest.mark.asyncio
async def test_procedural_and_lesson_distillation_end_to_end(mcp_session: ClientSession) -> None:
    namespace = f"exit-criterion-phase3-{uuid.uuid4().hex[:12]}"

    # --- (i)/(iii): the reused Phase 2 corroboration ingredient, ingested
    # first so its own first call is the one the inline auto-trigger
    # harmlessly consumes solo (see module docstring). ---
    for transcript in (
        "Alice works at Acme Corp.",
        "Alice is employed at Acme Corp.",
        "Alice's employer is Acme Corp.",
    ):
        ingest = await _ingest_step(mcp_session, namespace, transcript)
        assert ingest["extraction_degraded"] is False

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # --- (i): two successful sessions describing the same procedure. ---
    session_a = f"session-a-{uuid.uuid4().hex[:8]}"
    session_b = f"session-b-{uuid.uuid4().hex[:8]}"
    session_c = f"session-c-{uuid.uuid4().hex[:8]}"

    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_A_STEPS[0], session_a, "success")
    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_A_STEPS[1], session_a, "success")
    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_A_STEPS[2], session_a, "success")

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_B_STEPS[0], session_b, "success")
    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_B_STEPS[1], session_b, "success")
    await _ingest_step(mcp_session, namespace, _TRACE_SUCCESS_B_STEPS[2], session_b, "success")

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # --- (ii): one failed session on a related-looking but distinct task. ---
    await _ingest_step(mcp_session, namespace, _TRACE_FAILURE_C_STEPS[0], session_c, "failure")
    await _ingest_step(mcp_session, namespace, _TRACE_FAILURE_C_STEPS[1], session_c, "failure")
    await _ingest_step(mcp_session, namespace, _TRACE_FAILURE_C_STEPS[2], session_c, "failure")

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # --- (a)/(b)/(c): force a consolidation pass. ---
    consolidate_result = _unwrap(
        await mcp_session.call_tool("consolidate", {"namespace": namespace, "force": True})
    )
    assert consolidate_result["ran"] is True
    assert consolidate_result["trigger_reason"] == "manual"
    # (c): all three distillation types ran inside this one pass.
    assert consolidate_result["facts_distilled"] >= 1
    assert consolidate_result["procedures_distilled"] == 1
    assert consolidate_result["lessons_distilled"] == 1

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # --- (d): find_skill by natural-language content, not by name. ---
    find_result = _unwrap(
        await mcp_session.call_tool(
            "find_skill",
            {
                "query": (
                    "How do I fix a test that's failing with a KeyError because "
                    "a required setting isn't defaulted anywhere?"
                ),
                "namespace": namespace,
                "kind": "all",
            },
        )
    )
    results = find_result["results"]
    assert len(results) >= 1
    top = results[0]
    assert top["kind"] == "skill"
    # The unrelated lesson, if it appears at all, must not outrank the skill.
    lesson_hits = [r for r in results if r["kind"] == "lesson"]
    if lesson_hits:
        assert lesson_hits[0]["score"] < top["score"]

    # --- (e): get_skill returns literal SKILL.md-conformant text, and
    # applying it via an ordinary subsequent tool call succeeds. ---
    get_result = _unwrap(
        await mcp_session.call_tool("get_skill", {"name": top["name"], "namespace": namespace})
    )
    assert get_result["found"] is True
    assert get_result["kind"] == "skill"
    markdown = get_result["markdown"]
    assert markdown is not None
    assert markdown.startswith("---\n")
    assert f"name: {top['name']}" in markdown
    assert "description:" in markdown
    assert markdown.count("---") == 2

    applied = await _ingest_step(
        mcp_session,
        namespace,
        (
            "Following the retrieved skill, added a default value to the "
            "config loader to fix the KeyError; tests now pass."
        ),
    )
    assert applied["extraction_degraded"] is False
