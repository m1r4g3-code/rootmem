"""Tests `capture.ingest.ingest_transcript` against all four ports faked —
zero I/O, per NFR4 (docs/requirements/phase1-requirements.md)."""

from __future__ import annotations

import pytest

from rootmem.capture.ingest import ingest_transcript
from rootmem.embedding.protocols import EmbeddingError
from rootmem.extraction.fakes.scripted_provider import ScriptedExtractionProvider
from rootmem.extraction.models import ExtractedRelation, ExtractionResult
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository


class _StubEmbeddingProvider:
    """Not one of the two real embedding fakes (fixture-replay needs a
    fixed, recorded sentence set; a naive fake would work here too, but
    this local stub keeps the test independent of the fixture file's exact
    contents and lets it simulate failure, which neither real fake does)."""

    def __init__(self, vector: list[float] | None = None, fail: bool = False) -> None:
        self._vector = vector or [0.1, 0.2, 0.3]
        self._fail = fail

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._fail:
            raise EmbeddingError("simulated embedding failure")
        return [self._vector for _ in texts]


def _extraction_result(subject_name: str, object_name: str) -> ExtractionResult:
    return ExtractionResult(
        relations=[
            ExtractedRelation(
                subject_name=subject_name,
                subject_type="Person",
                predicate="works_at",
                object_name=object_name,
                object_type="Organization",
            )
        ]
    )


@pytest.mark.asyncio
async def test_successful_ingest_embeds_extracts_and_reports_counts() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider()
    extraction = ScriptedExtractionProvider(
        {"Alice works at Acme Corp": _extraction_result("Alice", "Acme Corp")}
    )

    result = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="Alice works at Acme Corp",
        source="test",
    )

    memory = await memory_repo.get_by_id("ns", result.memory_id)
    assert memory is not None
    assert memory.content_embedding == [0.1, 0.2, 0.3]
    assert result.embedded is True
    assert result.entities_extracted == 2


@pytest.mark.asyncio
async def test_session_outcome_is_persisted_on_the_stored_memory() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider()
    extraction = ScriptedExtractionProvider({"step one": _extraction_result("Alice", "Acme Corp")})

    result = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="step one",
        source="test",
        source_session_id="s1",
        session_outcome="success",
    )

    memory = await memory_repo.get_by_id("ns", result.memory_id)
    assert memory is not None
    assert memory.session_outcome == "success"
    assert memory.source_session_id == "s1"


@pytest.mark.asyncio
async def test_no_session_outcome_defaults_to_none() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider()
    extraction = ScriptedExtractionProvider(
        {"no outcome": _extraction_result("Alice", "Acme Corp")}
    )

    result = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="no outcome",
        source="test",
    )

    memory = await memory_repo.get_by_id("ns", result.memory_id)
    assert memory is not None
    assert memory.session_outcome is None
    assert result.relations_extracted == 1
    assert result.superseded_count == 0
    assert result.contested_count == 0
    assert result.extraction_degraded is False


@pytest.mark.asyncio
async def test_embedding_failure_degrades_but_still_stores_memory() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider(fail=True)
    extraction = ScriptedExtractionProvider({"some text": _extraction_result("Alice", "Acme Corp")})

    result = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="some text",
        source="test",
    )

    memory = await memory_repo.get_by_id("ns", result.memory_id)
    assert memory is not None
    assert memory.content_embedding is None
    assert result.embedded is False
    assert result.entities_extracted == 2  # extraction itself still ran fine


@pytest.mark.asyncio
async def test_extraction_failure_degrades_but_still_stores_memory() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider()
    extraction = ScriptedExtractionProvider()  # nothing registered -> always raises

    result = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="unregistered text",
        source="test",
    )

    memory = await memory_repo.get_by_id("ns", result.memory_id)
    assert memory is not None
    assert memory.content == "unregistered text"
    assert result.extraction_degraded is True
    assert result.entities_extracted == 0
    assert result.relations_extracted == 0


@pytest.mark.asyncio
async def test_second_ingest_supersedes_contradicting_relation() -> None:
    memory_repo = InMemoryMemoryRepository()
    graph_repo = InMemoryGraphRepository()
    embedding = _StubEmbeddingProvider()
    extraction = ScriptedExtractionProvider(
        {
            "Alice works at Acme Corp": _extraction_result("Alice", "Acme Corp"),
            "Alice joined Globex as an engineer": _extraction_result("Alice", "Globex"),
        }
    )

    await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="Alice works at Acme Corp",
        source="test",
    )
    second = await ingest_transcript(
        memory_repo,
        graph_repo,
        embedding,
        extraction,
        namespace="ns",
        content="Alice joined Globex as an engineer",
        source="test",
    )

    assert second.superseded_count == 1
    assert second.contested_count == 0
