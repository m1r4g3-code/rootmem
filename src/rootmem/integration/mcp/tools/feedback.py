"""`feedback` — the retrieval-outcome signal ADR 0008 named as Phase 2's own
trigger condition, and ADR 0014's answer to what that signal concretely is:
an explicit, agent-reported outcome, not an inferred one.
"""

from __future__ import annotations

from rootmem.integration.mcp.schemas import FeedbackParams, FeedbackResult, RelationView
from rootmem.observability.metrics import log_operation
from rootmem.storage.graph_protocols import GraphRepository


@log_operation("feedback")
async def feedback(graph_repository: GraphRepository, params: FeedbackParams) -> FeedbackResult:
    relation = await graph_repository.record_feedback(
        params.namespace,
        params.relation_id,
        outcome=params.outcome,
        reported_confidence=params.confidence,
        note=params.note,
    )
    return FeedbackResult(relation=RelationView.from_record(relation))
