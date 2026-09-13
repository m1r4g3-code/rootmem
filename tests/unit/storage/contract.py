"""Shared behavioral contract for every `MemoryRepository` implementation.

Both `InMemoryMemoryRepository` and `PostgresMemoryRepository` are run
against this same suite (see test_in_memory_repository.py and
tests/integration/test_postgres_roundtrip.py) so the fake and the real
backend can't silently drift apart in behavior — this is what makes it
safe to unit-test tool handlers against the fake alone.

This module is a base class, not a test file itself (no `test_` prefix),
so pytest doesn't try to collect it directly — it's collected only via the
subclasses that provide a `repository` fixture.
"""

from __future__ import annotations

import pytest

from rootmem.storage.models import MemoryUpdate, NewMemory
from rootmem.storage.protocols import MemoryRepository, NotFoundError


class MemoryRepositoryContract:
    """Subclass and provide an async `repository` fixture yielding a fresh
    `MemoryRepository` for each test."""

    @pytest.fixture
    def repository(self) -> MemoryRepository:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    async def test_create_then_get_by_id(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="the sky is blue", source="test")
        )

        fetched = await repository.get_by_id("ns", created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.content == "the sky is blue"
        assert fetched.schema_version == 1
        assert fetched.deleted_at is None

    async def test_get_by_id_wrong_namespace_returns_none(
        self, repository: MemoryRepository
    ) -> None:
        created = await repository.create(
            NewMemory(namespace="ns-a", content="secret", source="test")
        )

        assert await repository.get_by_id("ns-b", created.id) is None

    async def test_get_by_id_missing_returns_none(self, repository: MemoryRepository) -> None:
        assert await repository.get_by_id("ns", "does-not-exist") is None

    async def test_create_and_get_by_key(self, repository: MemoryRepository) -> None:
        await repository.create(
            NewMemory(namespace="ns", key="fact-1", content="water boils at 100C", source="test")
        )

        fetched = await repository.get_by_key("ns", "fact-1")

        assert fetched is not None
        assert fetched.content == "water boils at 100C"

    async def test_idempotency_key_dedupes_within_namespace(
        self, repository: MemoryRepository
    ) -> None:
        first = await repository.create(
            NewMemory(
                namespace="ns",
                content="first write",
                source="test",
                idempotency_key="dedupe-me",
            )
        )
        second = await repository.create(
            NewMemory(
                namespace="ns",
                content="second write with same key",
                source="test",
                idempotency_key="dedupe-me",
            )
        )

        assert second.id == first.id
        assert second.content == "first write"

    async def test_idempotency_key_scoped_per_namespace(
        self, repository: MemoryRepository
    ) -> None:
        a = await repository.create(
            NewMemory(namespace="ns-a", content="in a", source="test", idempotency_key="same-key")
        )
        b = await repository.create(
            NewMemory(namespace="ns-b", content="in b", source="test", idempotency_key="same-key")
        )

        assert a.id != b.id

    async def test_update_content_and_confidence(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="old fact", source="test", confidence=0.5)
        )

        updated = await repository.update(
            created.id, MemoryUpdate(content="new fact", confidence=0.9)
        )

        assert updated.content == "new fact"
        assert updated.confidence == 0.9
        assert updated.updated_at >= created.updated_at

    async def test_update_missing_raises_not_found(self, repository: MemoryRepository) -> None:
        with pytest.raises(NotFoundError):
            await repository.update("does-not-exist", MemoryUpdate(content="x"))

    async def test_update_deleted_raises_not_found(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="soon deleted", source="test")
        )
        await repository.soft_delete(created.id, reason="test cleanup")

        with pytest.raises(NotFoundError):
            await repository.update(created.id, MemoryUpdate(content="x"))

    async def test_soft_delete_excludes_from_get_by_id_and_key(
        self, repository: MemoryRepository
    ) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", key="k", content="to delete", source="test")
        )

        await repository.soft_delete(created.id, reason="no longer needed")

        assert await repository.get_by_id("ns", created.id) is None
        assert await repository.get_by_key("ns", "k") is None

    async def test_soft_delete_is_idempotent(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="to delete twice", source="test")
        )

        first = await repository.soft_delete(created.id, reason="first")
        second = await repository.soft_delete(created.id, reason="second")

        assert second.deleted_at == first.deleted_at
        assert second.deleted_reason == "first"

    async def test_soft_delete_missing_raises_not_found(
        self, repository: MemoryRepository
    ) -> None:
        with pytest.raises(NotFoundError):
            await repository.soft_delete("does-not-exist", reason=None)

    async def test_search_text_finds_matching_content(
        self, repository: MemoryRepository
    ) -> None:
        await repository.create(
            NewMemory(namespace="ns", content="the quick brown fox", source="test")
        )
        await repository.create(
            NewMemory(namespace="ns", content="an unrelated sentence", source="test")
        )

        results = await repository.search_text("ns", "brown fox", limit=10)

        assert len(results) == 1
        assert "brown fox" in results[0].record.content

    async def test_search_text_excludes_soft_deleted(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="findable fact", source="test")
        )
        await repository.soft_delete(created.id, reason=None)

        results = await repository.search_text("ns", "findable", limit=10)

        assert results == []

    async def test_search_text_respects_namespace(self, repository: MemoryRepository) -> None:
        await repository.create(
            NewMemory(namespace="ns-a", content="shared term xyz", source="test")
        )

        results = await repository.search_text("ns-b", "xyz", limit=10)

        assert results == []

    async def test_search_text_respects_limit(self, repository: MemoryRepository) -> None:
        for i in range(5):
            await repository.create(
                NewMemory(namespace="ns", content=f"repeated term {i}", source="test")
            )

        results = await repository.search_text("ns", "repeated", limit=2)

        assert len(results) == 2

    async def test_search_text_filters_by_source(self, repository: MemoryRepository) -> None:
        await repository.create(
            NewMemory(namespace="ns", content="alpha value", source="claude-code")
        )
        await repository.create(NewMemory(namespace="ns", content="alpha value", source="cursor"))

        results = await repository.search_text("ns", "alpha", limit=10, source="cursor")

        assert len(results) == 1
        assert results[0].record.source == "cursor"
