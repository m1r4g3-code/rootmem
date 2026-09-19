"""Consolidation orchestration (ADR 0012/0016/0020): fetch a batch of
unconsolidated episodes, score their salience, cluster near-duplicates,
distill qualifying clusters into semantic relations, group episodes into
session traces and distill qualifying ones into procedural memories/lessons,
and mark the batch processed.

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
from rootmem.consolidation.procedural_clustering import (
    SessionTrace,
    build_trace_pairs,
    group_session_traces,
)
from rootmem.consolidation.procedural_protocols import (
    ProceduralDistillationContext,
    ProceduralDistillationError,
    ProceduralDistillationProvider,
)
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
from rootmem.consolidation.skill_format import (
    SkillFormatError,
    validate_skill_description,
    validate_skill_name,
)
from rootmem.consolidation.trigger import TriggerSettings, should_consolidate
from rootmem.embedding.protocols import EmbeddingError, EmbeddingProvider
from rootmem.extraction.pipeline import apply_extraction
from rootmem.logging import get_logger
from rootmem.storage.consolidation_protocols import ConsolidationRepository, ConsolidationRun
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.models import MemoryRecord
from rootmem.storage.procedural_protocols import NewProceduralMemory, ProceduralMemoryRepository
from rootmem.storage.protocols import MemoryRepository


async def run_consolidation(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    embedding_provider: EmbeddingProvider,
    procedural_memory_repository: ProceduralMemoryRepository,
    procedural_distillation_provider: ProceduralDistillationProvider,
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

    procedures_distilled, lessons_distilled = await _distill_procedural_memories(
        episodes,
        namespace,
        embedding_provider,
        procedural_memory_repository,
        procedural_distillation_provider,
        settings,
    )

    await memory_repository.mark_consolidated(memory_ids, datetime.now(UTC))

    return await consolidation_repository.complete_run(
        run.id,
        episodes_processed=len(episodes),
        clusters_formed=clusters_formed,
        facts_distilled=facts_distilled,
        procedures_distilled=procedures_distilled,
        lessons_distilled=lessons_distilled,
    )


async def _distill_procedural_memories(
    episodes: list[MemoryRecord],
    namespace: str,
    embedding_provider: EmbeddingProvider,
    procedural_memory_repository: ProceduralMemoryRepository,
    procedural_distillation_provider: ProceduralDistillationProvider,
    settings: Settings,
) -> tuple[int, int]:
    """The episodic->procedural / failure->lesson stage (ADR 0017/0020),
    run against the same already-fetched batch the episodic->semantic stage
    above used. Returns `(procedures_distilled, lessons_distilled)`."""
    traces = group_session_traces(
        episodes, min_session_length=settings.procedural_min_session_length
    )
    if not traces:
        return 0, 0

    try:
        embeddings = await embedding_provider.embed([t.summary_text for t in traces])
    except EmbeddingError as exc:
        # Graceful degradation, same discipline as DistillationError below --
        # no embeddings means no clustering signal, so this pass simply
        # skips procedural/lesson distillation rather than failing the run.
        get_logger().warning("operation=embed_session_traces outcome=degraded error=%s", exc)
        return 0, 0
    trace_embeddings = {
        trace.session_id: embedding for trace, embedding in zip(traces, embeddings, strict=True)
    }
    traces_by_session_id = {t.session_id: t for t in traces}

    success_traces = [t for t in traces if t.outcome == "success"]
    failure_traces = [t for t in traces if t.outcome == "failure"]

    procedures_distilled = 0
    if success_traces:
        success_embeddings = {t.session_id: trace_embeddings[t.session_id] for t in success_traces}
        pairs = build_trace_pairs(success_embeddings)
        clusters = cluster_by_similarity(
            list(success_embeddings),
            pairs,
            threshold=settings.procedural_session_similarity_threshold,
        )
        for cluster in clusters:
            if len(cluster) < settings.procedural_min_recurrence:
                continue
            cluster_traces = [traces_by_session_id[session_id] for session_id in cluster]
            persisted = await _distill_one_procedural_memory(
                cluster_traces,
                "skill",
                namespace,
                procedural_memory_repository,
                procedural_distillation_provider,
                settings,
            )
            if persisted:
                procedures_distilled += 1

    lessons_distilled = 0
    for trace in failure_traces:
        # A single failed trace already meets the recurrence gate unless
        # lesson_min_recurrence has been raised above its default of 1.
        if settings.lesson_min_recurrence > 1:
            continue
        persisted = await _distill_one_procedural_memory(
            [trace],
            "lesson",
            namespace,
            procedural_memory_repository,
            procedural_distillation_provider,
            settings,
        )
        if persisted:
            lessons_distilled += 1

    return procedures_distilled, lessons_distilled


async def _distill_one_procedural_memory(
    cluster_traces: list[SessionTrace],
    kind: Literal["skill", "lesson"],
    namespace: str,
    procedural_memory_repository: ProceduralMemoryRepository,
    procedural_distillation_provider: ProceduralDistillationProvider,
    settings: Settings,
) -> bool:
    """Distill one skill/lesson from `cluster_traces`, validate it against
    the SKILL.md spec (NFR10), and persist it with provenance links to every
    source episode. Returns whether it was actually persisted -- a
    `ProceduralDistillationError`/`SkillFormatError` degrades this one
    candidate (logged, skipped), never aborts the rest of the pass."""
    try:
        draft = await procedural_distillation_provider.distill_procedure(
            [trace.steps for trace in cluster_traces],
            ProceduralDistillationContext(namespace=namespace, kind=kind),
        )
        validate_skill_name(draft.name, max_length=settings.skill_name_max_length)
        validate_skill_description(
            draft.description, max_length=settings.skill_description_max_length
        )
    except (ProceduralDistillationError, SkillFormatError) as exc:
        get_logger().warning("operation=distill_procedure outcome=degraded error=%s", exc)
        return False

    record = await procedural_memory_repository.create(
        NewProceduralMemory(
            namespace=namespace,
            kind=kind,
            name=draft.name,
            description=draft.description,
            body_markdown=draft.body_markdown,
        )
    )
    for trace in cluster_traces:
        for memory_id in trace.memory_ids:
            await procedural_memory_repository.link_provenance(record.id, memory_id)
    return True


async def maybe_run_consolidation(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    embedding_provider: EmbeddingProvider,
    procedural_memory_repository: ProceduralMemoryRepository,
    procedural_distillation_provider: ProceduralDistillationProvider,
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
        embedding_provider,
        procedural_memory_repository,
        procedural_distillation_provider,
        namespace,
        decision.trigger_reason,
        settings,
    )
