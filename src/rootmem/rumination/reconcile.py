"""The rumination reconciliation decision (ADR 0049/0050,
docs/math-spec/phase8-math-spec.md). Pure, zero I/O — reuses
`extraction.contradiction.belief_confidence` and `retrieval.decay.retention`
over a pair of relations rather than inventing new math.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from rootmem.extraction.contradiction import belief_confidence
from rootmem.retrieval.decay import RetentionParams, retention

if TYPE_CHECKING:
    from rootmem.storage.graph_models import RelationRecord


@dataclass(frozen=True)
class ReconciliationDecision:
    action: Literal["resolve", "still_contested"]
    # Present only when action == "resolve".
    winner_id: str | None = None
    loser_id: str | None = None


def decayed_confidence(relation: RelationRecord, now: datetime, params: RetentionParams) -> float:
    """`belief_confidence * retention` — relations carry no access-tracking,
    so `retention` reduces to a flat function of elapsed time since
    `recorded_at` alone (access_count=0, salience=None)."""
    return belief_confidence(relation.belief_alpha, relation.belief_beta) * retention(
        now, None, relation.recorded_at, 0, None, params
    )


def decide_reconciliation(
    older: RelationRecord,
    newer: RelationRecord,
    now: datetime,
    decay_params: RetentionParams,
    supersede_margin: float,
) -> ReconciliationDecision:
    """`older`/`newer` must be the two active, contested sides of one
    `(namespace, subject_entity_id, predicate)` pair, `older.recorded_at <=
    newer.recorded_at`. Compares decay-adjusted confidence using the same
    margin `extraction.contradiction.resolve_contradiction` already uses for
    fresh evidence -- the decision shape is identical, only the inputs
    differ (decayed confidence, not raw)."""
    d_older = decayed_confidence(older, now, decay_params)
    d_newer = decayed_confidence(newer, now, decay_params)

    if d_newer > d_older + supersede_margin:
        return ReconciliationDecision(action="resolve", winner_id=newer.id, loser_id=older.id)
    if d_older > d_newer + supersede_margin:
        return ReconciliationDecision(action="resolve", winner_id=older.id, loser_id=newer.id)
    return ReconciliationDecision(action="still_contested")
