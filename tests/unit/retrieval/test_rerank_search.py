"""`search` with multi-factor re-ranking (ADR 0022), against the in-memory fakes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rootmem.config import Settings
from rootmem.embedding.fakes.fixture_provider import FixtureReplayEmbeddingProvider
from rootmem.integration.mcp.schemas import SearchParams
from rootmem.integration.mcp.tools.search import search
from rootmem.retrieval.rerank import RankingContext
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.graph_models import NewEntity
from rootmem.storage.models import NewMemory

NS = "rank-ns"


def _settings() -> Settings:
    return Settings(
        trust_source_reliability={"trusted": 0.95, "shady": 0.2},
    )


def _ctx() -> RankingContext:
    return RankingContext.from_settings(_settings())


def _params(**overrides: object) -> SearchParams:
    base: dict[str, object] = {"query": "deploy checklist", "namespace": NS, "mode": "text"}
    base.update(overrides)
    return SearchParams(**base)


@pytest.fixture
def repo() -> InMemoryMemoryRepository:
    return InMemoryMemoryRepository()


@pytest.fixture
def embeddings() -> FixtureReplayEmbeddingProvider:
    return FixtureReplayEmbeddingProvider()


async def _add(repo: InMemoryMemoryRepository, content: str, source: str = "manual") -> str:
    record = await repo.create(NewMemory(namespace=NS, content=content, source=source))
    return record.id


async def test_reinforced_memory_outranks_stale_one_and_breakdown_sums(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    reinforced = await _add(repo, "deploy checklist alpha")
    stale = await _add(repo, "deploy checklist alpha")
    later = datetime.now(UTC) + timedelta(days=30)
    for _ in range(5):
        await repo.record_access([reinforced], later - timedelta(days=1))

    response = await search(repo, embeddings, _params(as_of=later), ranking=_ctx())

    assert [item.id for item in response.results][0] == reinforced
    assert {item.id for item in response.results} == {reinforced, stale}
    for item in response.results:
        assert item.breakdown is not None
        assert sum(item.breakdown.values()) == pytest.approx(item.score)
        assert "retention" in item.breakdown


async def test_trusted_source_outranks_untrusted_at_equal_relevance(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    shady = await _add(repo, "deploy checklist beta", source="shady")
    trusted = await _add(repo, "deploy checklist beta", source="trusted")

    response = await search(repo, embeddings, _params(), ranking=_ctx())

    assert [item.id for item in response.results] == [trusted, shady]


async def test_graph_proximity_lifts_memory_linked_to_named_entity(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    graph = InMemoryGraphRepository()
    unlinked = await _add(repo, "deploy checklist gamma")
    linked = await _add(repo, "deploy checklist gamma")
    entity = await graph.upsert_entity(
        NewEntity(namespace=NS, entity_type="service", name="Payments")
    )
    await graph.link_memory_entity(linked, entity.id)

    response = await search(
        repo,
        embeddings,
        _params(entity_name="Payments", entity_type="service"),
        ranking=_ctx(),
        graph_repository=graph,
    )

    assert [item.id for item in response.results] == [linked, unlinked]
    assert response.results[0].breakdown is not None
    assert response.results[0].breakdown["graph_proximity"] > 0


async def test_unknown_entity_drops_the_term_instead_of_penalizing(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    await _add(repo, "deploy checklist delta")

    response = await search(
        repo,
        embeddings,
        _params(entity_name="Nobody", entity_type="service"),
        ranking=_ctx(),
        graph_repository=InMemoryGraphRepository(),
    )

    assert response.results[0].breakdown is not None
    assert "graph_proximity" not in response.results[0].breakdown


async def test_normal_search_records_access_but_as_of_does_not(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    memory_id = await _add(repo, "deploy checklist epsilon")

    await search(repo, embeddings, _params(as_of=datetime.now(UTC)), ranking=_ctx())
    untouched = await repo.get_by_id(NS, memory_id)
    assert untouched is not None and untouched.access_count == 0

    await search(repo, embeddings, _params(), ranking=_ctx())
    touched = await repo.get_by_id(NS, memory_id)
    assert touched is not None and touched.access_count == 1


async def test_forgotten_memories_never_surface(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    gone = await _add(repo, "deploy checklist zeta")
    await repo.soft_delete(gone, reason="test")

    response = await search(repo, embeddings, _params(), ranking=_ctx())

    assert response.results == []


async def test_without_ranking_context_behaves_as_before(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    await _add(repo, "deploy checklist eta")

    response = await search(repo, embeddings, _params())

    assert len(response.results) == 1
    assert response.results[0].breakdown is None


async def test_limit_is_respected_after_overfetch(
    repo: InMemoryMemoryRepository, embeddings: FixtureReplayEmbeddingProvider
) -> None:
    for i in range(6):
        await _add(repo, f"deploy checklist theta {i}")

    response = await search(repo, embeddings, _params(limit=2), ranking=_ctx())

    assert len(response.results) == 2


def test_entity_name_and_type_must_come_together() -> None:
    with pytest.raises(ValueError):
        SearchParams(query="q", entity_name="X")
