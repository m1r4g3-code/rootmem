"""`consolidate` — run one consolidation pass on demand (ADR 0012),
checking the trigger condition first unless `force=True` bypasses it.
"""

from __future__ import annotations

from rootmem.config import Settings
from rootmem.consolidation.distill import maybe_run_consolidation
from rootmem.consolidation.protocols import DistillationProvider
from rootmem.integration.mcp.schemas import ConsolidateParams, ConsolidateResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.consolidation_protocols import ConsolidationRepository
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.protocols import MemoryRepository


@log_operation("consolidate")
async def consolidate(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    settings: Settings,
    params: ConsolidateParams,
) -> ConsolidateResult:
    result = await maybe_run_consolidation(
        memory_repository,
        graph_repository,
        consolidation_repository,
        distillation_provider,
        params.namespace,
        settings,
        force=params.force,
    )
    if result is None:
        return ConsolidateResult(ran=False)
    return ConsolidateResult(
        ran=True,
        trigger_reason=result.trigger_reason,
        episodes_processed=result.episodes_processed,
        clusters_formed=result.clusters_formed,
        facts_distilled=result.facts_distilled,
    )
