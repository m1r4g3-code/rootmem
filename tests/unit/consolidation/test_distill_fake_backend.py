"""Tests `consolidation.distill.run_consolidation`/`maybe_run_consolidation`
against all fake ports -- zero I/O, per NFR5
(docs/requirements/phase2-requirements.md)."""

from __future__ import annotations

import pytest

from rootmem.config import Settings
from rootmem.consolidation.distill import maybe_run_consolidation, run_consolidation
from rootmem.consolidation.fakes.scripted_distillation_provider import ScriptedDistillationProvider
from rootmem.extraction.models import ExtractedEntity, ExtractedRelation, ExtractionResult
from rootmem.storage.fakes.in_memory_consolidation_repository import InMemoryConsolidationRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.models import NewMemory

_UNIT_VECTOR_0 = [1.0] + [0.0] * 1023
_UNIT_VECTOR_1 = [0.0, 1.0] + [0.0] * 1022


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_consolidation_with_no_unconsolidated_episodes_completes_with_zero_counts() -> (
    None
):
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()

    run = await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    assert run.completed_at is not None
    assert run.episodes_processed == 0
    assert run.clusters_formed == 0
    assert run.facts_distilled == 0


@pytest.mark.asyncio
async def test_run_consolidation_marks_all_processed_episodes_consolidated() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    a = await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))
    b = await memory_repo.create(NewMemory(namespace="ns", content="another fact", source="test"))

    run = await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    assert run.episodes_processed == 2
    assert await memory_repo.count_unconsolidated("ns") == 0
    fetched_a = await memory_repo.get_by_id("ns", a.id)
    fetched_b = await memory_repo.get_by_id("ns", b.id)
    assert fetched_a is not None and fetched_a.consolidated_at is not None
    assert fetched_b is not None and fetched_b.consolidated_at is not None


@pytest.mark.asyncio
async def test_run_consolidation_computes_salience_for_every_episode() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    created = await memory_repo.create(
        NewMemory(namespace="ns", content="a fact", source="test", importance_flag=1.0)
    )
    assert created.salience_score is None

    await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    fetched = await memory_repo.get_by_id("ns", created.id)
    assert fetched is not None
    assert fetched.salience_score is not None
    assert fetched.salience_score > 0.0


@pytest.mark.asyncio
async def test_run_consolidation_clusters_near_duplicates_and_distills() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    texts = ["Alice works at Acme Corp", "Alice is employed at Acme Corp"]
    for text in texts:
        await memory_repo.create(
            NewMemory(namespace="ns", content=text, source="test", content_embedding=_UNIT_VECTOR_0)
        )
    distillation.register(
        texts,
        ExtractionResult(
            entities=[
                ExtractedEntity(name="Alice", entity_type="Person"),
                ExtractedEntity(name="Acme Corp", entity_type="Organization"),
            ],
            relations=[
                ExtractedRelation(
                    subject_name="Alice",
                    subject_type="Person",
                    predicate="works_at",
                    object_name="Acme Corp",
                    object_type="Organization",
                    confidence=0.95,
                )
            ],
        ),
    )

    run = await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    assert run.clusters_formed == 1
    assert run.facts_distilled == 1
    alice = await graph_repo.find_entity_by_name("ns", "Person", "Alice")
    assert alice is not None
    related = await graph_repo.related("ns", alice.id, max_hops=1)
    assert len(related) == 1
    assert related[0].derivation == "distilled"
    provenance = await graph_repo.get_relation_provenance("ns", related[0].id)
    assert len(provenance) == 2


@pytest.mark.asyncio
async def test_singleton_below_min_cluster_size_is_consolidated_but_not_distilled() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    lone = await memory_repo.create(
        NewMemory(
            namespace="ns", content="a lone fact", source="test", content_embedding=_UNIT_VECTOR_1
        )
    )

    run = await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    assert run.facts_distilled == 0
    fetched = await memory_repo.get_by_id("ns", lone.id)
    assert fetched is not None
    assert fetched.consolidated_at is not None


@pytest.mark.asyncio
async def test_distillation_failure_degrades_gracefully() -> None:
    """NFR2's discipline extended to consolidation: one cluster's
    distillation failure never aborts the whole pass."""
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()  # nothing registered -> always fails
    for text in ["fact one", "fact one restated"]:
        await memory_repo.create(
            NewMemory(namespace="ns", content=text, source="test", content_embedding=_UNIT_VECTOR_0)
        )

    run = await run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", "manual", _settings()
    )

    assert run.facts_distilled == 0
    assert run.episodes_processed == 2
    assert await memory_repo.count_unconsolidated("ns") == 0


@pytest.mark.asyncio
async def test_maybe_run_consolidation_no_ops_when_trigger_not_met() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    settings = _settings(consolidation_episode_threshold=500, consolidation_time_window_hours=24.0)
    # A namespace with no prior run at all is always time-eligible by design
    # (see test_trigger.py's own test_no_prior_run_always_triggers) -- a
    # recent prior run establishes the baseline the "not met" case actually
    # tests against.
    await consolidation_repo.start_run("ns", "manual")
    await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))

    result = await maybe_run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", settings
    )

    assert result is None


@pytest.mark.asyncio
async def test_maybe_run_consolidation_force_always_runs() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()

    result = await maybe_run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", _settings(), force=True
    )

    assert result is not None
    assert result.trigger_reason == "manual"


@pytest.mark.asyncio
async def test_maybe_run_consolidation_triggers_on_count_threshold() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    consolidation_repo = InMemoryConsolidationRepository()
    distillation = ScriptedDistillationProvider()
    await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))
    settings = _settings(consolidation_episode_threshold=1)

    result = await maybe_run_consolidation(
        memory_repo, graph_repo, consolidation_repo, distillation, "ns", settings
    )

    assert result is not None
    assert result.trigger_reason == "count"
