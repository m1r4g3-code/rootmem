"""Exercises the tool-handler business logic (rootmem.integration.mcp.tools)
against the in-memory fake — no MCP protocol layer, no Docker. The MCP
protocol layer itself (argument flattening, exception translation) is
covered separately in tests/integration/test_mcp_server_e2e.py, which
requires a real subprocess and is Docker/stdio-dependent."""

from __future__ import annotations

import pytest

from rootmem.config import Settings
from rootmem.consolidation.fakes.scripted_distillation_provider import ScriptedDistillationProvider
from rootmem.consolidation.fakes.scripted_procedural_distillation_provider import (
    ScriptedProceduralDistillationProvider,
)
from rootmem.extraction.fakes.scripted_provider import ScriptedExtractionProvider
from rootmem.extraction.models import ExtractedRelation, ExtractionResult
from rootmem.integration.mcp.schemas import (
    ConsolidateParams,
    FeedbackParams,
    FindSkillParams,
    ForgetParams,
    GetSkillParams,
    IngestSessionParams,
    RecallParams,
    RelatedParams,
    RememberParams,
    SearchParams,
    UpdateParams,
)
from rootmem.integration.mcp.tools.consolidate import consolidate
from rootmem.integration.mcp.tools.feedback import feedback
from rootmem.integration.mcp.tools.find_skill import find_skill
from rootmem.integration.mcp.tools.forget import forget
from rootmem.integration.mcp.tools.get_skill import get_skill
from rootmem.integration.mcp.tools.ingest_session import ingest_session
from rootmem.integration.mcp.tools.recall import recall
from rootmem.integration.mcp.tools.related import related
from rootmem.integration.mcp.tools.remember import remember
from rootmem.integration.mcp.tools.search import search
from rootmem.integration.mcp.tools.update import update
from rootmem.storage.fakes.in_memory_consolidation_repository import InMemoryConsolidationRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.models import NewMemory
from rootmem.storage.procedural_protocols import NewProceduralMemory
from rootmem.storage.protocols import NotFoundError


class _StubEmbeddingProvider:
    """A minimal EmbeddingProvider fake — these tests exercise tool-handler
    business logic (validation, not-found semantics, idempotency), not
    semantic search quality (that's tests/unit/storage/contract.py's job),
    so a fixed vector for every input is sufficient here."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture
def repository() -> InMemoryMemoryRepository:
    return InMemoryMemoryRepository()


@pytest.fixture
def embedding_provider() -> _StubEmbeddingProvider:
    return _StubEmbeddingProvider()


async def test_remember_then_recall_by_id(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    remembered = await remember(
        repository, embedding_provider, RememberParams(content="the sky is blue", source="test")
    )

    recalled = await recall(repository, RecallParams(id=remembered.id))

    assert recalled.found is True
    assert recalled.record is not None
    assert recalled.record.content == "the sky is blue"


async def test_remember_then_recall_by_key(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    await remember(
        repository,
        embedding_provider,
        RememberParams(content="water boils at 100C", key="boiling-point", source="test"),
    )

    recalled = await recall(repository, RecallParams(key="boiling-point"))

    assert recalled.found is True
    assert recalled.record is not None
    assert recalled.record.content == "water boils at 100C"


async def test_recall_missing_returns_not_found_result(
    repository: InMemoryMemoryRepository,
) -> None:
    recalled = await recall(repository, RecallParams(id="does-not-exist"))

    assert recalled.found is False
    assert recalled.record is None


async def test_remember_idempotency_key_returns_same_id(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    first = await remember(
        repository,
        embedding_provider,
        RememberParams(content="first", source="test", idempotency_key="dedupe"),
    )
    second = await remember(
        repository,
        embedding_provider,
        RememberParams(content="second", source="test", idempotency_key="dedupe"),
    )

    assert second.id == first.id


async def test_update_changes_content(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    remembered = await remember(
        repository, embedding_provider, RememberParams(content="old", source="test")
    )

    updated = await update(repository, UpdateParams(id=remembered.id, content="new"))

    recalled = await recall(repository, RecallParams(id=remembered.id))
    assert updated.id == remembered.id
    assert recalled.record is not None
    assert recalled.record.content == "new"


async def test_update_missing_raises_not_found(repository: InMemoryMemoryRepository) -> None:
    with pytest.raises(NotFoundError):
        await update(repository, UpdateParams(id="does-not-exist", content="x"))


async def test_forget_then_recall_reports_not_found(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    remembered = await remember(
        repository, embedding_provider, RememberParams(content="to forget", source="test")
    )

    forgotten = await forget(repository, ForgetParams(id=remembered.id, reason="test cleanup"))
    recalled = await recall(repository, RecallParams(id=remembered.id))

    assert forgotten.id == remembered.id
    assert recalled.found is False


async def test_forget_is_idempotent(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    remembered = await remember(
        repository, embedding_provider, RememberParams(content="to forget twice", source="test")
    )

    first = await forget(repository, ForgetParams(id=remembered.id))
    second = await forget(repository, ForgetParams(id=remembered.id))

    assert second.deleted_at == first.deleted_at


async def test_forget_missing_raises_not_found(repository: InMemoryMemoryRepository) -> None:
    with pytest.raises(NotFoundError):
        await forget(repository, ForgetParams(id="does-not-exist"))


async def test_search_finds_matching_content(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    """mode="text" here specifically: this test is exercising Phase 0's
    exact full-text behavior, not hybrid ranking — with every memory
    sharing the same stub embedding, hybrid mode's vector term would score
    unrelated content identically to the match, which isn't what this test
    is about (see tests/unit/storage/contract.py for real hybrid-ranking
    coverage)."""
    await remember(
        repository, embedding_provider, RememberParams(content="the quick brown fox", source="test")
    )
    await remember(
        repository,
        embedding_provider,
        RememberParams(content="an unrelated sentence", source="test"),
    )

    response = await search(
        repository, embedding_provider, SearchParams(query="brown fox", mode="text")
    )

    assert len(response.results) == 1
    assert "brown fox" in response.results[0].content


async def test_search_excludes_forgotten_memories(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    remembered = await remember(
        repository, embedding_provider, RememberParams(content="findable fact", source="test")
    )
    await forget(repository, ForgetParams(id=remembered.id))

    response = await search(
        repository, embedding_provider, SearchParams(query="findable", mode="text")
    )

    assert response.results == []


async def test_related_returns_not_found_for_unknown_entity() -> None:
    graph_repository = InMemoryGraphRepository()

    result = await related(
        graph_repository, RelatedParams(entity_name="Nobody", entity_type="Person")
    )

    assert result.entity_found is False
    assert result.relations == []


async def test_ingest_session_stores_memory_and_extracts_graph(
    repository: InMemoryMemoryRepository, embedding_provider: _StubEmbeddingProvider
) -> None:
    graph_repository = InMemoryGraphRepository()
    extraction_provider = ScriptedExtractionProvider(
        {
            "Alice works at Acme Corp": ExtractionResult(
                relations=[
                    ExtractedRelation(
                        subject_name="Alice",
                        subject_type="Person",
                        predicate="works_at",
                        object_name="Acme Corp",
                        object_type="Organization",
                    )
                ]
            )
        }
    )

    result = await ingest_session(
        repository,
        graph_repository,
        embedding_provider,
        extraction_provider,
        IngestSessionParams(transcript="Alice works at Acme Corp", source="test"),
    )

    memory = await repository.get_by_id("default", result.memory_id)
    assert memory is not None
    assert result.relations_extracted == 1
    assert result.extraction_degraded is False

    related_result = await related(
        graph_repository, RelatedParams(entity_name="Alice", entity_type="Person")
    )
    assert related_result.entity_found is True
    assert len(related_result.relations) == 1


async def test_consolidate_force_runs_and_reports_no_facts_without_clusters(
    repository: InMemoryMemoryRepository,
    embedding_provider: _StubEmbeddingProvider,
) -> None:
    graph_repository = InMemoryGraphRepository()
    consolidation_repository = InMemoryConsolidationRepository()
    distillation_provider = ScriptedDistillationProvider()
    procedural_memory_repository = InMemoryProceduralMemoryRepository()
    procedural_distillation_provider = ScriptedProceduralDistillationProvider()
    await repository.create(NewMemory(namespace="default", content="a lone fact", source="test"))

    result = await consolidate(
        repository,
        graph_repository,
        consolidation_repository,
        distillation_provider,
        embedding_provider,
        procedural_memory_repository,
        procedural_distillation_provider,
        Settings(),
        ConsolidateParams(force=True),
    )

    assert result.ran is True
    assert result.trigger_reason == "manual"
    assert result.episodes_processed == 1
    assert result.facts_distilled == 0
    assert result.procedures_distilled == 0
    assert result.lessons_distilled == 0


async def test_consolidate_no_ops_when_trigger_not_met(
    repository: InMemoryMemoryRepository,
    embedding_provider: _StubEmbeddingProvider,
) -> None:
    graph_repository = InMemoryGraphRepository()
    consolidation_repository = InMemoryConsolidationRepository()
    distillation_provider = ScriptedDistillationProvider()
    procedural_memory_repository = InMemoryProceduralMemoryRepository()
    procedural_distillation_provider = ScriptedProceduralDistillationProvider()
    await consolidation_repository.start_run("default", "manual")

    result = await consolidate(
        repository,
        graph_repository,
        consolidation_repository,
        distillation_provider,
        embedding_provider,
        procedural_memory_repository,
        procedural_distillation_provider,
        Settings(consolidation_episode_threshold=500, consolidation_time_window_hours=24.0),
        ConsolidateParams(),
    )

    assert result.ran is False


async def test_feedback_confirmed_raises_relation_confidence() -> None:
    graph_repository = InMemoryGraphRepository()
    alice = await graph_repository.upsert_entity(
        NewEntity(namespace="default", entity_type="Person", name="Alice")
    )
    acme = await graph_repository.upsert_entity(
        NewEntity(namespace="default", entity_type="Organization", name="Acme")
    )
    resolution = await graph_repository.create_relation(
        NewRelation(
            namespace="default",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=acme.id,
            confidence=0.9,
        )
    )

    result = await feedback(
        graph_repository,
        FeedbackParams(relation_id=resolution.new.id, outcome="confirmed", confidence=1.0),
    )

    assert result.relation.confidence > resolution.new.confidence


async def test_feedback_missing_relation_raises_not_found() -> None:
    graph_repository = InMemoryGraphRepository()

    with pytest.raises(NotFoundError):
        await feedback(
            graph_repository,
            FeedbackParams(relation_id="00000000-0000-0000-0000-000000000000", outcome="confirmed"),
        )


async def test_get_skill_returns_conformant_markdown_for_an_active_skill(
    embedding_provider: _StubEmbeddingProvider,
) -> None:
    procedural_memory_repository = InMemoryProceduralMemoryRepository()
    await procedural_memory_repository.create(
        NewProceduralMemory(
            namespace="default",
            kind="skill",
            name="fix-missing-config-default",
            description="Use this when a test fails with a KeyError from a missing default.",
            body_markdown="1. Find the missing default.\n2. Add it.",
        )
    )

    result = await get_skill(
        procedural_memory_repository, GetSkillParams(name="fix-missing-config-default")
    )

    assert result.found is True
    assert result.kind == "skill"
    assert result.markdown is not None
    assert result.markdown.startswith("---\n")
    assert "name: fix-missing-config-default" in result.markdown


async def test_get_skill_not_found_returns_found_false() -> None:
    procedural_memory_repository = InMemoryProceduralMemoryRepository()

    result = await get_skill(procedural_memory_repository, GetSkillParams(name="no-such-skill"))

    assert result.found is False
    assert result.markdown is None


async def test_find_skill_ranks_matching_skill_over_unrelated_one(
    embedding_provider: _StubEmbeddingProvider,
) -> None:
    procedural_memory_repository = InMemoryProceduralMemoryRepository()
    await procedural_memory_repository.create(
        NewProceduralMemory(
            namespace="default",
            kind="skill",
            name="fix-missing-config-default",
            description="Use this when a test fails with a KeyError from a missing default.",
            body_markdown="config default keyerror",
        )
    )
    await procedural_memory_repository.create(
        NewProceduralMemory(
            namespace="default",
            kind="lesson",
            name="unrelated-docker-lesson",
            description="Use this when a docker build hangs.",
            body_markdown="docker build cache",
        )
    )

    result = await find_skill(
        procedural_memory_repository,
        embedding_provider,
        FindSkillParams(query="missing config default keyerror"),
    )

    assert len(result.results) == 1
    assert result.results[0].name == "fix-missing-config-default"
