"""Exercises the tool-handler business logic (rootmem.integration.mcp.tools)
against the in-memory fake — no MCP protocol layer, no Docker. The MCP
protocol layer itself (argument flattening, exception translation) is
covered separately in tests/integration/test_mcp_server_e2e.py, which
requires a real subprocess and is Docker/stdio-dependent."""

from __future__ import annotations

import pytest

from rootmem.integration.mcp.schemas import (
    ForgetParams,
    RecallParams,
    RememberParams,
    SearchParams,
    UpdateParams,
)
from rootmem.integration.mcp.tools.forget import forget
from rootmem.integration.mcp.tools.recall import recall
from rootmem.integration.mcp.tools.remember import remember
from rootmem.integration.mcp.tools.search import search
from rootmem.integration.mcp.tools.update import update
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.protocols import NotFoundError


@pytest.fixture
def repository() -> InMemoryMemoryRepository:
    return InMemoryMemoryRepository()


async def test_remember_then_recall_by_id(repository: InMemoryMemoryRepository) -> None:
    remembered = await remember(
        repository, RememberParams(content="the sky is blue", source="test")
    )

    recalled = await recall(repository, RecallParams(id=remembered.id))

    assert recalled.found is True
    assert recalled.record is not None
    assert recalled.record.content == "the sky is blue"


async def test_remember_then_recall_by_key(repository: InMemoryMemoryRepository) -> None:
    await remember(
        repository,
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
    repository: InMemoryMemoryRepository,
) -> None:
    first = await remember(
        repository,
        RememberParams(content="first", source="test", idempotency_key="dedupe"),
    )
    second = await remember(
        repository,
        RememberParams(content="second", source="test", idempotency_key="dedupe"),
    )

    assert second.id == first.id


async def test_update_changes_content(repository: InMemoryMemoryRepository) -> None:
    remembered = await remember(repository, RememberParams(content="old", source="test"))

    updated = await update(repository, UpdateParams(id=remembered.id, content="new"))

    recalled = await recall(repository, RecallParams(id=remembered.id))
    assert updated.id == remembered.id
    assert recalled.record is not None
    assert recalled.record.content == "new"


async def test_update_missing_raises_not_found(repository: InMemoryMemoryRepository) -> None:
    with pytest.raises(NotFoundError):
        await update(repository, UpdateParams(id="does-not-exist", content="x"))


async def test_forget_then_recall_reports_not_found(
    repository: InMemoryMemoryRepository,
) -> None:
    remembered = await remember(repository, RememberParams(content="to forget", source="test"))

    forgotten = await forget(repository, ForgetParams(id=remembered.id, reason="test cleanup"))
    recalled = await recall(repository, RecallParams(id=remembered.id))

    assert forgotten.id == remembered.id
    assert recalled.found is False


async def test_forget_is_idempotent(repository: InMemoryMemoryRepository) -> None:
    remembered = await remember(
        repository, RememberParams(content="to forget twice", source="test")
    )

    first = await forget(repository, ForgetParams(id=remembered.id))
    second = await forget(repository, ForgetParams(id=remembered.id))

    assert second.deleted_at == first.deleted_at


async def test_forget_missing_raises_not_found(repository: InMemoryMemoryRepository) -> None:
    with pytest.raises(NotFoundError):
        await forget(repository, ForgetParams(id="does-not-exist"))


async def test_search_finds_matching_content(repository: InMemoryMemoryRepository) -> None:
    await remember(repository, RememberParams(content="the quick brown fox", source="test"))
    await remember(repository, RememberParams(content="an unrelated sentence", source="test"))

    response = await search(repository, SearchParams(query="brown fox"))

    assert len(response.results) == 1
    assert "brown fox" in response.results[0].content


async def test_search_excludes_forgotten_memories(repository: InMemoryMemoryRepository) -> None:
    remembered = await remember(repository, RememberParams(content="findable fact", source="test"))
    await forget(repository, ForgetParams(id=remembered.id))

    response = await search(repository, SearchParams(query="findable"))

    assert response.results == []
