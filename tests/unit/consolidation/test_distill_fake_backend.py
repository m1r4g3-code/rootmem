"""Tests `consolidation.distill.run_consolidation`/`maybe_run_consolidation`
against all fake ports -- zero I/O, per NFR5
(docs/requirements/phase2-requirements.md/docs/requirements/phase3-requirements.md)."""

from __future__ import annotations

import pytest

from rootmem.config import Settings
from rootmem.consolidation.distill import maybe_run_consolidation, run_consolidation
from rootmem.consolidation.fakes.scripted_distillation_provider import ScriptedDistillationProvider
from rootmem.consolidation.fakes.scripted_procedural_distillation_provider import (
    ScriptedProceduralDistillationProvider,
)
from rootmem.consolidation.skill_format import SkillDraft
from rootmem.embedding.fakes.fixture_provider import FixtureReplayEmbeddingProvider
from rootmem.extraction.models import ExtractedEntity, ExtractedRelation, ExtractionResult
from rootmem.storage.fakes.in_memory_consolidation_repository import InMemoryConsolidationRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.models import NewMemory

_UNIT_VECTOR_0 = [1.0] + [0.0] * 1023
_UNIT_VECTOR_1 = [0.0, 1.0] + [0.0] * 1022

# The exact Phase 3 session-trace sentences recorded by
# scripts/record_voyage_fixture.py -- real voyage-4 embeddings, validated by
# scripts/spike_session_trace_clustering.py to cluster/separate correctly.
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


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _deps() -> tuple[
    InMemoryMemoryRepository,
    InMemoryGraphRepository,
    InMemoryConsolidationRepository,
    ScriptedDistillationProvider,
    FixtureReplayEmbeddingProvider,
    InMemoryProceduralMemoryRepository,
    ScriptedProceduralDistillationProvider,
]:
    return (
        InMemoryMemoryRepository(),
        InMemoryGraphRepository(),
        InMemoryConsolidationRepository(),
        ScriptedDistillationProvider(),
        FixtureReplayEmbeddingProvider(),
        InMemoryProceduralMemoryRepository(),
        ScriptedProceduralDistillationProvider(),
    )


@pytest.mark.asyncio
async def test_run_consolidation_with_no_unconsolidated_episodes_completes_with_zero_counts() -> (
    None
):
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.completed_at is not None
    assert run.episodes_processed == 0
    assert run.clusters_formed == 0
    assert run.facts_distilled == 0
    assert run.procedures_distilled == 0
    assert run.lessons_distilled == 0


@pytest.mark.asyncio
async def test_run_consolidation_marks_all_processed_episodes_consolidated() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    a = await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))
    b = await memory_repo.create(NewMemory(namespace="ns", content="another fact", source="test"))

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.episodes_processed == 2
    assert await memory_repo.count_unconsolidated("ns") == 0
    fetched_a = await memory_repo.get_by_id("ns", a.id)
    fetched_b = await memory_repo.get_by_id("ns", b.id)
    assert fetched_a is not None and fetched_a.consolidated_at is not None
    assert fetched_b is not None and fetched_b.consolidated_at is not None


@pytest.mark.asyncio
async def test_run_consolidation_computes_salience_for_every_episode() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    created = await memory_repo.create(
        NewMemory(namespace="ns", content="a fact", source="test", importance_flag=1.0)
    )
    assert created.salience_score is None

    await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    fetched = await memory_repo.get_by_id("ns", created.id)
    assert fetched is not None
    assert fetched.salience_score is not None
    assert fetched.salience_score > 0.0


@pytest.mark.asyncio
async def test_run_consolidation_clusters_near_duplicates_and_distills() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
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
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
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
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    lone = await memory_repo.create(
        NewMemory(
            namespace="ns", content="a lone fact", source="test", content_embedding=_UNIT_VECTOR_1
        )
    )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.facts_distilled == 0
    fetched = await memory_repo.get_by_id("ns", lone.id)
    assert fetched is not None
    assert fetched.consolidated_at is not None


@pytest.mark.asyncio
async def test_distillation_failure_degrades_gracefully() -> None:
    """NFR2's discipline extended to consolidation: one cluster's
    distillation failure never aborts the whole pass."""
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    # nothing registered -> distillation always fails
    for text in ["fact one", "fact one restated"]:
        await memory_repo.create(
            NewMemory(namespace="ns", content=text, source="test", content_embedding=_UNIT_VECTOR_0)
        )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.facts_distilled == 0
    assert run.episodes_processed == 2
    assert await memory_repo.count_unconsolidated("ns") == 0


@pytest.mark.asyncio
async def test_maybe_run_consolidation_no_ops_when_trigger_not_met() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    settings = _settings(consolidation_episode_threshold=500, consolidation_time_window_hours=24.0)
    # A namespace with no prior run at all is always time-eligible by design
    # (see test_trigger.py's own test_no_prior_run_always_triggers) -- a
    # recent prior run establishes the baseline the "not met" case actually
    # tests against.
    await consolidation_repo.start_run("ns", "manual")
    await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))

    result = await maybe_run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        settings,
    )

    assert result is None


@pytest.mark.asyncio
async def test_maybe_run_consolidation_force_always_runs() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )

    result = await maybe_run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        _settings(),
        force=True,
    )

    assert result is not None
    assert result.trigger_reason == "manual"


@pytest.mark.asyncio
async def test_maybe_run_consolidation_triggers_on_count_threshold() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    await memory_repo.create(NewMemory(namespace="ns", content="a fact", source="test"))
    settings = _settings(consolidation_episode_threshold=1)

    result = await maybe_run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        settings,
    )

    assert result is not None
    assert result.trigger_reason == "count"


async def _ingest_trace(
    memory_repo: InMemoryMemoryRepository, session_id: str, outcome: str, steps: list[str]
) -> None:
    for step in steps:
        await memory_repo.create(
            NewMemory(
                namespace="ns",
                content=step,
                source="test",
                source_session_id=session_id,
                session_outcome=outcome,
            )
        )


@pytest.mark.asyncio
async def test_two_successful_traces_of_the_same_procedure_distill_into_one_skill() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    await _ingest_trace(memory_repo, "s1", "success", _TRACE_SUCCESS_A_STEPS)
    await _ingest_trace(memory_repo, "s2", "success", _TRACE_SUCCESS_B_STEPS)
    proc_dist.register(
        [_TRACE_SUCCESS_A_STEPS, _TRACE_SUCCESS_B_STEPS],
        SkillDraft(
            name="fix-missing-config-default",
            description="Use this when a test fails with a KeyError from a missing default.",
            body_markdown="1. Find the missing default.\n2. Add it.",
        ),
    )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.procedures_distilled == 1
    assert run.lessons_distilled == 0
    skill = await proc_repo.get_by_name("ns", "fix-missing-config-default")
    assert skill is not None
    assert skill.kind == "skill"
    provenance = await proc_repo.get_provenance("ns", skill.id)
    assert len(provenance) == 6


@pytest.mark.asyncio
async def test_single_successful_trace_does_not_meet_recurrence_and_is_not_distilled() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    await _ingest_trace(memory_repo, "s1", "success", _TRACE_SUCCESS_A_STEPS)

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.procedures_distilled == 0


@pytest.mark.asyncio
async def test_single_failed_trace_distills_into_one_lesson_with_no_recurrence_required() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    await _ingest_trace(memory_repo, "s3", "failure", _TRACE_FAILURE_C_STEPS)
    proc_dist.register(
        [_TRACE_FAILURE_C_STEPS],
        SkillDraft(
            name="avoid-input-type-fix-for-serialization-bugs",
            description="Use this before changing an input type to fix a TypeError.",
            body_markdown="The real cause was a serialization bug, not the input type.",
        ),
    )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.lessons_distilled == 1
    lesson = await proc_repo.get_by_name("ns", "avoid-input-type-fix-for-serialization-bugs")
    assert lesson is not None
    assert lesson.kind == "lesson"


@pytest.mark.asyncio
async def test_procedural_distillation_failure_degrades_gracefully() -> None:
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    await _ingest_trace(memory_repo, "s1", "success", _TRACE_SUCCESS_A_STEPS)
    await _ingest_trace(memory_repo, "s2", "success", _TRACE_SUCCESS_B_STEPS)
    # Nothing registered on proc_dist -> distill_procedure always raises.

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.procedures_distilled == 0
    # The episodes are still marked consolidated even though procedural
    # distillation degraded for this cluster.
    assert await memory_repo.count_unconsolidated("ns") == 0


@pytest.mark.asyncio
async def test_facts_and_procedures_and_lessons_all_distill_in_one_pass() -> None:
    """The coexistence proof the Phase 3 exit criterion itself relies on:
    episodic->semantic, episodic->procedural, and failure->lesson
    distillation all run inside one consolidation pass (ADR 0020)."""
    memory_repo, graph_repo, consolidation_repo, distillation, embedding, proc_repo, proc_dist = (
        _deps()
    )
    fact_texts = ["Bob works at Globex", "Bob is employed at Globex"]
    for text in fact_texts:
        await memory_repo.create(
            NewMemory(namespace="ns", content=text, source="test", content_embedding=_UNIT_VECTOR_0)
        )
    distillation.register(
        fact_texts,
        ExtractionResult(
            entities=[
                ExtractedEntity(name="Bob", entity_type="Person"),
                ExtractedEntity(name="Globex", entity_type="Organization"),
            ],
            relations=[
                ExtractedRelation(
                    subject_name="Bob",
                    subject_type="Person",
                    predicate="works_at",
                    object_name="Globex",
                    object_type="Organization",
                    confidence=0.95,
                )
            ],
        ),
    )
    await _ingest_trace(memory_repo, "s1", "success", _TRACE_SUCCESS_A_STEPS)
    await _ingest_trace(memory_repo, "s2", "success", _TRACE_SUCCESS_B_STEPS)
    await _ingest_trace(memory_repo, "s3", "failure", _TRACE_FAILURE_C_STEPS)
    proc_dist.register(
        [_TRACE_SUCCESS_A_STEPS, _TRACE_SUCCESS_B_STEPS],
        SkillDraft(name="a-skill", description="d", body_markdown="b"),
    )
    proc_dist.register(
        [_TRACE_FAILURE_C_STEPS],
        SkillDraft(name="a-lesson", description="d", body_markdown="b"),
    )

    run = await run_consolidation(
        memory_repo,
        graph_repo,
        consolidation_repo,
        distillation,
        embedding,
        proc_repo,
        proc_dist,
        "ns",
        "manual",
        _settings(),
    )

    assert run.facts_distilled == 1
    assert run.procedures_distilled == 1
    assert run.lessons_distilled == 1
