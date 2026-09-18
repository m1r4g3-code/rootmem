"""The Phase 2 exit criterion (docs/requirements/phase2-requirements.md),
proven end-to-end via the real MCP server subprocess, real Postgres, real
Voyage embeddings, and real Anthropic extraction/distillation — no fakes
anywhere in this test.

Scenario: three corroborating restatements of "Alice works at Acme Corp"
go in via `ingest_session`, plus one novel fact flagged important, followed
by a forced `consolidate` pass, then a genuine contradiction ("Alice joined
Globex"), then an explicit `feedback` call. The system must, via MCP alone:

(a) after `consolidate(force=True)`, the three near-duplicate episodes
    cluster and distill into the *same* relation the per-episode extraction
    already created (corroboration, not a second row — see ADR 0013),
    upgrading its `derivation` to `"distilled"` and linking
    `relation_provenance` to all three source episodes — provable via
    `related`;
(b) every episode has a `salience_score`, and the flagged-important, novel
    one-off memory scores measurably higher than a routine, unflagged,
    redundant restatement — provable via `recall`;
(c) the three corroborating restatements (plus the fourth, distillation-
    sourced corroboration event from (a)) measurably raise the relation's
    `confidence` above what a single extraction alone would produce;
(d) the Globex contradiction, a fresh single-shot extraction, does not
    clear the now-strengthened relation's posterior by the required margin
    — it contests rather than supersedes, proving corroboration earned the
    original relation real resistance a fresh, uncorroborated fact would
    not have had (Phase 1's flat floor gave no such protection);
(e) an explicit `feedback(outcome="confirmed")` call on the contested
    original relation raises its confidence again, resolving the ambiguity
    the contest left open — the literal, concrete answer to what ADR 0008
    called "retrieval-outcome feedback."

Marked `integration_external` (real Voyage + Anthropic + distillation
calls, real money per run, NFR6) — the automated sign-off gate for tagging
`v0.2.0-phase2`.

Paced deliberately, same rationale as Phase 1's exit-criterion test: this
account's Voyage tier is hard-capped at 3 requests/minute. Five embedding
calls are needed total (three corroborating ingests, one important-fact
ingest, one Globex ingest) — `consolidate` itself makes zero new embedding
calls, since it reads already-stored vectors via `find_similar_pairs`. A
single pacing sleep after the first three keeps every 60-second window
under budget.
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
    """See tests/integration/test_phase1_exit_criterion.py's identical
    helper for why this is the honest, mypy-satisfying shape."""
    assert result.is_error is not True, f"tool call failed: {result.content}"
    assert result.structured_content is not None
    return cast("dict[str, Any]", result.structured_content)


@pytest.mark.asyncio
async def test_corroboration_distillation_and_bayesian_contradiction_end_to_end(
    mcp_session: ClientSession,
) -> None:
    namespace = f"exit-criterion-phase2-{uuid.uuid4().hex[:12]}"

    # --- Three corroborating restatements (the exact sentences already
    # validated by scripts/spike_similarity_clustering.py to cluster
    # correctly at distillation_similarity_threshold=0.80 against real
    # voyage-4 embeddings) ---
    restatement_memory_ids: list[str] = []
    for transcript in (
        "Alice works at Acme Corp.",
        "Alice is employed at Acme Corp.",
        "Alice's employer is Acme Corp.",
    ):
        ingest = _unwrap(
            await mcp_session.call_tool(
                "ingest_session",
                {"transcript": transcript, "source": "exit-criterion-test", "namespace": namespace},
            )
        )
        assert ingest["extraction_degraded"] is False
        restatement_memory_ids.append(ingest["memory_id"])

    # (c) baseline: confidence after just the corroboration-time behavior
    # already exercised above (three extraction-time corroboration events,
    # per ADR 0013 -- no new row per restatement, one relation strengthened
    # three times).
    related_after_restatements = _unwrap(
        await mcp_session.call_tool(
            "related",
            {"entity_name": "Alice", "entity_type": "Person", "namespace": namespace},
        )
    )
    assert related_after_restatements["entity_found"] is True
    relations_after_restatements = related_after_restatements["relations"]
    assert len(relations_after_restatements) == 1
    original_relation = relations_after_restatements[0]
    assert original_relation["derivation"] == "extracted"
    confidence_after_restatements = original_relation["confidence"]

    await asyncio.sleep(_RATE_LIMIT_PACING_SECONDS)

    # --- One novel, one-off, flagged-important fact ---
    important_ingest = _unwrap(
        await mcp_session.call_tool(
            "ingest_session",
            {
                "transcript": (
                    "The quarterly board meeting was unexpectedly moved to a "
                    "private location due to a security threat."
                ),
                "source": "exit-criterion-test",
                "namespace": namespace,
                "importance_flag": 1.0,
            },
        )
    )
    important_memory_id = important_ingest["memory_id"]

    # --- (a)/(b): force a consolidation pass ---
    # Not asserting episodes_processed == 4 here: the very first
    # ingest_session call above into this brand-new namespace already fired
    # ingest_session's own inline auto-trigger (ADR 0012) in the
    # background -- a namespace with no prior consolidation run is always
    # time-eligible (see consolidation/trigger.py's should_consolidate), so
    # that first restatement was silently consolidated solo (a singleton,
    # too small to cluster/distill on its own) well before this explicit
    # call runs, minutes later. What matters for (a) is that the *other*
    # two restatements are still there to cluster together explicitly.
    consolidate_result = _unwrap(
        await mcp_session.call_tool("consolidate", {"namespace": namespace, "force": True})
    )
    assert consolidate_result["ran"] is True
    assert consolidate_result["trigger_reason"] == "manual"
    assert consolidate_result["clusters_formed"] >= 1
    assert consolidate_result["facts_distilled"] >= 1

    # (a): the distillation cluster corroborated the *same* relation
    # (ADR 0013) rather than creating a second row -- derivation upgraded,
    # provenance links all three restatements.
    related_after_consolidation = _unwrap(
        await mcp_session.call_tool(
            "related",
            {"entity_name": "Alice", "entity_type": "Person", "namespace": namespace},
        )
    )
    relations_after_consolidation = related_after_consolidation["relations"]
    assert len(relations_after_consolidation) == 1
    strengthened_relation = relations_after_consolidation[0]
    assert strengthened_relation["id"] == original_relation["id"]
    assert strengthened_relation["derivation"] == "distilled"
    assert sorted(strengthened_relation["source_memory_ids"]) == sorted(restatement_memory_ids)

    # (c): the distillation-sourced corroboration event is a fourth piece
    # of evidence on top of the three extraction-time ones -- confidence
    # keeps rising, it doesn't plateau or reset.
    assert strengthened_relation["confidence"] > confidence_after_restatements

    # (b): a flagged-important, novel one-off memory scores measurably
    # higher than a routine, unflagged, redundant restatement.
    important_record = _unwrap(
        await mcp_session.call_tool("recall", {"id": important_memory_id, "namespace": namespace})
    )
    assert important_record["found"] is True
    important_salience = important_record["record"]["salience_score"]
    assert important_salience is not None

    redundant_record = _unwrap(
        await mcp_session.call_tool(
            "recall", {"id": restatement_memory_ids[1], "namespace": namespace}
        )
    )
    assert redundant_record["found"] is True
    redundant_salience = redundant_record["record"]["salience_score"]
    assert redundant_salience is not None

    assert important_salience > redundant_salience

    # --- (d): a genuine contradiction against the now-strengthened relation ---
    globex_ingest = _unwrap(
        await mcp_session.call_tool(
            "ingest_session",
            {
                "transcript": "Alice joined Globex as an engineer.",
                "source": "exit-criterion-test",
                "namespace": namespace,
            },
        )
    )
    assert globex_ingest["extraction_degraded"] is False
    # The actual proof: a fresh, single-shot contradiction against a
    # relation corroborated four times over does NOT clear the margin --
    # it contests rather than supersedes, unlike Phase 1's flat floor,
    # which would have superseded outright on confidence alone.
    assert globex_ingest["superseded_count"] == 0
    assert globex_ingest["contested_count"] == 1

    related_after_contradiction = _unwrap(
        await mcp_session.call_tool(
            "related",
            {"entity_name": "Alice", "entity_type": "Person", "namespace": namespace},
        )
    )
    relations_after_contradiction = related_after_contradiction["relations"]
    assert len(relations_after_contradiction) == 2
    assert all(r["is_contested"] for r in relations_after_contradiction)
    assert all(r["is_active"] for r in relations_after_contradiction)  # contest never supersedes

    # --- (e): explicit feedback resolves the ambiguity the contest left open ---
    feedback_result = _unwrap(
        await mcp_session.call_tool(
            "feedback",
            {
                "relation_id": strengthened_relation["id"],
                "namespace": namespace,
                "outcome": "confirmed",
                "confidence": 1.0,
            },
        )
    )
    assert feedback_result["relation"]["confidence"] > strengthened_relation["confidence"]
