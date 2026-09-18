"""Consolidation orchestration (ADR 0012/0016): fetch a batch of
unconsolidated episodes, score their salience, cluster near-duplicates,
distill qualifying clusters into semantic relations, and mark the batch
processed.

Pure orchestration, dependency-injected exactly like `capture.ingest`
(ADR 0003's pattern) — fully unit-testable against fakes with zero I/O,
wired to real adapters only in `server.py`/`consolidation/cli.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal

from rootmem.config import Settings
from rootmem.consolidation.clustering import cluster_by_similarity
from rootmem.consolidation.protocols import (
    DistillationContext,
    DistillationError,
    DistillationProvider,
)
from rootmem.consolidation.salience import (
    SalienceWeights,
    compute_novelty,
    compute_repetition,
    compute_salience,
)
from rootmem.consolidation.trigger import TriggerSettings, should_consolidate
from rootmem.extraction.pipeline import apply_extraction
from rootmem.logging import get_logger
from rootmem.storage.consolidation_protocols import ConsolidationRepository, ConsolidationRun
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.protocols import MemoryRepository


async def run_consolidation(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    namespace: str,
    trigger_reason: Literal["count", "time", "manual"],
    settings: Settings,
) -> ConsolidationRun:
    """Run exactly one consolidation pass, unconditionally (the trigger
    decision is the caller's job — see `maybe_run_consolidation` below)."""
    run = await consolidation_repository.start_run(namespace, trigger_reason)

    episodes = await memory_repository.list_unconsolidated(
        namespace, limit=settings.consolidation_batch_size
    )
    if not episodes:
        return await consolidation_repository.complete_run(
            run.id, episodes_processed=0, clusters_formed=0, facts_distilled=0
        )

    memory_ids = [e.id for e in episodes]
    episodes_by_id = {e.id: e for e in episodes}

    # One pgvector self-join serves both salience's novelty/repetition terms
    # and distillation clustering -- threshold=0.0 returns the full
    # pairwise distribution within the batch, not just qualifying pairs.
    pairs = await memory_repository.find_similar_pairs(namespace, memory_ids, threshold=0.0)

    similarities_by_memory: dict[str, list[float]] = defaultdict(list)
    for id_a, id_b, similarity in pairs:
        similarities_by_memory[id_a].append(similarity)
        similarities_by_memory[id_b].append(similarity)

    salience_weights = SalienceWeights.from_settings(settings)
    for episode in episodes:
        neighbor_similarities = similarities_by_memory[episode.id][
            : settings.novelty_neighbor_sample_size
        ]
        novelty = compute_novelty(neighbor_similarities)
        repetition = compute_repetition(neighbor_similarities, salience_weights)
        salience = compute_salience(
            novelty=novelty,
            importance_flag=episode.importance_flag,
            repetition=repetition,
            task_relevance=0.0,
            weights=salience_weights,
        )
        await memory_repository.update_salience(episode.id, salience)

    clusters = cluster_by_similarity(
        memory_ids, pairs, threshold=settings.distillation_similarity_threshold
    )
    clusters_formed = sum(1 for cluster in clusters if len(cluster) >= 2)

    facts_distilled = 0
    for cluster in clusters:
        if len(cluster) < settings.distillation_min_cluster_size:
            continue
        texts = [episodes_by_id[memory_id].content for memory_id in cluster]
        try:
            extraction_result = await distillation_provider.distill(
                texts, DistillationContext(namespace=namespace)
            )
        except DistillationError as exc:
            # NFR2's "fail the one thing, not the process" discipline: one
            # cluster's distillation failure never aborts the whole pass --
            # those episodes are still marked consolidated below, just
            # without a distilled fact this time.
            get_logger().warning("operation=distill outcome=degraded error=%s", exc)
            continue

        await apply_extraction(
            graph_repository,
            namespace,
            extraction_result,
            source_memory_ids=cluster,
            derivation="distilled",
        )
        facts_distilled += 1

    await memory_repository.mark_consolidated(memory_ids, datetime.now(UTC))

    return await consolidation_repository.complete_run(
        run.id,
        episodes_processed=len(episodes),
        clusters_formed=clusters_formed,
        facts_distilled=facts_distilled,
    )


async def maybe_run_consolidation(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    namespace: str,
    settings: Settings,
    force: bool = False,
) -> ConsolidationRun | None:
    """Check the trigger condition (ADR 0012) and run a consolidation pass
    only if it's met (or `force=True`) — returns None on a clean no-op.
    Shared by the `consolidate` MCP tool, `consolidation/cli.py`, and
    `ingest_session`'s inline auto-trigger, so the check-then-run logic
    lives in exactly one place."""
    unconsolidated_count = await memory_repository.count_unconsolidated(namespace)
    last_run = await consolidation_repository.get_last_run(namespace)
    decision = should_consolidate(
        unconsolidated_count=unconsolidated_count,
        last_run=last_run,
        now=datetime.now(UTC),
        settings=TriggerSettings.from_settings(settings),
        force=force,
    )
    if not decision.should_run:
        return None
    assert decision.trigger_reason is not None
    return await run_consolidation(
        memory_repository,
        graph_repository,
        consolidation_repository,
        distillation_provider,
        namespace,
        decision.trigger_reason,
        settings,
    )
