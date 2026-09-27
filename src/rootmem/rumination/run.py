"""Orchestrates one rumination pass (ADR 0049): discover contested pairs,
decide, resolve, audit. Called by both the autonomous loop (`namespace=None`,
cross-namespace) and the explicit `ruminate` MCP tool (one namespace, through
the ordinary `guarded`/`authorize_namespace` wrapper like every other tool).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from rootmem.retrieval.decay import RetentionParams
from rootmem.rumination.reconcile import decide_reconciliation

if TYPE_CHECKING:
    from rootmem.audit.recorder import AuditRecorder
    from rootmem.storage.graph_models import RelationRecord
    from rootmem.storage.graph_protocols import GraphRepository

RUMINATION_ACTOR = "system:rumination"


@dataclass(frozen=True)
class RuminationSummary:
    pairs_examined: int
    pairs_resolved: int
    pairs_skipped_too_young: int
    pairs_skipped_ambiguous: int


def _group_pairs(
    contested: list[RelationRecord],
) -> dict[tuple[str, str, str], list[RelationRecord]]:
    groups: dict[tuple[str, str, str], list[RelationRecord]] = {}
    for relation in contested:
        key = (relation.namespace, relation.subject_entity_id, relation.predicate)
        groups.setdefault(key, []).append(relation)
    return groups


async def run_rumination_pass(
    graph_repository: GraphRepository,
    audit_recorder: AuditRecorder,
    *,
    now: datetime,
    namespace: str | None,
    decay_base_stability_days: float,
    supersede_margin: float,
    min_contest_age_hours: float,
    force: bool = False,
) -> RuminationSummary:
    contested = await graph_repository.list_contested(namespace)
    groups = _group_pairs(contested)
    decay_params = RetentionParams(base_stability_days=decay_base_stability_days)

    examined = resolved = skipped_young = skipped_ambiguous = 0

    for (group_namespace, _subject, _predicate), members in groups.items():
        if len(members) != 2:
            # A third contradiction arrived before the first was resolved --
            # a named, accepted limitation (research memo): left for a later
            # pass once the group returns to exactly two members.
            skipped_ambiguous += 1
            continue

        older, newer = sorted(members, key=lambda r: r.recorded_at)
        examined += 1

        if not force:
            youngest_recorded_at = newer.recorded_at
            age_hours = (now - youngest_recorded_at).total_seconds() / 3600
            if age_hours < min_contest_age_hours:
                skipped_young += 1
                continue

        decision = decide_reconciliation(older, newer, now, decay_params, supersede_margin)
        if decision.action == "still_contested":
            continue

        assert decision.winner_id is not None
        assert decision.loser_id is not None
        await graph_repository.resolve_contest(
            group_namespace, winner_id=decision.winner_id, loser_id=decision.loser_id, now=now
        )
        await audit_recorder.record(
            group_namespace,
            "ruminate_resolve",
            "relation",
            decision.winner_id,
            {"loser_id": decision.loser_id},
        )
        resolved += 1

    return RuminationSummary(
        pairs_examined=examined,
        pairs_resolved=resolved,
        pairs_skipped_too_young=skipped_young,
        pairs_skipped_ambiguous=skipped_ambiguous,
    )


__all__ = ["RUMINATION_ACTOR", "RuminationSummary", "run_rumination_pass"]
