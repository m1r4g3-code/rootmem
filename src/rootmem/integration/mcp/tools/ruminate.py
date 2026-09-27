"""`ruminate` — run one rumination pass on demand, scoped to one namespace
(ADR 0049/0052). The autonomous, cross-namespace loop this same logic backs
is `rumination.loop.run_rumination_loop`, wired in `server.py`'s
`main_async` only in HTTP mode -- this tool is the manual/testing path
through the ordinary `guarded`/`authorize_namespace` wrapper every other
tool uses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rootmem.audit.recorder import AuditRecorder
from rootmem.config import Settings
from rootmem.integration.mcp.schemas import RuminateParams, RuminateResult
from rootmem.observability.metrics import log_operation
from rootmem.rumination.run import run_rumination_pass
from rootmem.storage.graph_protocols import GraphRepository


@log_operation("ruminate")
async def ruminate(
    graph_repository: GraphRepository,
    audit_recorder: AuditRecorder,
    settings: Settings,
    params: RuminateParams,
) -> RuminateResult:
    summary = await run_rumination_pass(
        graph_repository,
        audit_recorder,
        now=datetime.now(UTC),
        namespace=params.namespace,
        decay_base_stability_days=settings.decay_base_stability_days,
        supersede_margin=settings.bayesian_supersede_margin,
        min_contest_age_hours=settings.rumination_min_contest_age_hours,
        force=params.force,
    )
    return RuminateResult(
        pairs_examined=summary.pairs_examined,
        pairs_resolved=summary.pairs_resolved,
        pairs_skipped_too_young=summary.pairs_skipped_too_young,
        pairs_skipped_ambiguous=summary.pairs_skipped_ambiguous,
    )
