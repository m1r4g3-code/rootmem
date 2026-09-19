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

from datetime import UTC, datetime

import pytest

from rootmem.storage.models import MemoryUpdate, NewMemory
from rootmem.storage.protocols import MemoryRepository, NotFoundError

# The real Postgres column is VECTOR(1024) (ADR 0007) — the in-memory fake
# doesn't care about dimension, but a shared contract test needs vectors
# that work against both, so these are full 1024-dim, differing only in
# which single dimension is set to 1.0 (still trivially "close" vs "far").
_EMBEDDING_DIM = 1024


def _unit_vector(hot_index: int) -> list[float]:
    vector = [0.0] * _EMBEDDING_DIM
    vector[hot_index] = 1.0
    return vector


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

    async def test_idempotency_key_scoped_per_namespace(self, repository: MemoryRepository) -> None:
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

    async def test_soft_delete_missing_raises_not_found(self, repository: MemoryRepository) -> None:
        with pytest.raises(NotFoundError):
            await repository.soft_delete("does-not-exist", reason=None)

    async def test_search_text_finds_matching_content(self, repository: MemoryRepository) -> None:
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

    async def test_search_semantic_ranks_by_cosine_similarity(
        self, repository: MemoryRepository
    ) -> None:
        close = await repository.create(
            NewMemory(
                namespace="ns",
                content="close match",
                source="test",
                content_embedding=_unit_vector(0),
            )
        )
        far = await repository.create(
            NewMemory(
                namespace="ns",
                content="far match",
                source="test",
                content_embedding=_unit_vector(1),
            )
        )

        results = await repository.search_semantic("ns", _unit_vector(0), limit=10)

        assert [r.record.id for r in results] == [close.id, far.id]

    async def test_search_semantic_excludes_records_without_embedding(
        self, repository: MemoryRepository
    ) -> None:
        await repository.create(
            NewMemory(namespace="ns", content="no embedding here", source="test")
        )

        results = await repository.search_semantic("ns", _unit_vector(0), limit=10)

        assert results == []

    async def test_search_hybrid_finds_purely_semantic_match_with_no_lexical_overlap(
        self, repository: MemoryRepository
    ) -> None:
        """The exit criterion's core claim: hybrid search must find a match
        via the embedding alone when there's zero shared vocabulary with the
        query — proving the vector component does real work (see
        docs/requirements/phase1-requirements.md's exit criterion, part c)."""
        semantic_match = await repository.create(
            NewMemory(
                namespace="ns",
                content="Globex Corporation hired a new software engineer last week",
                source="test",
                content_embedding=_unit_vector(0),
            )
        )
        await repository.create(
            NewMemory(
                namespace="ns",
                content="a completely different sentence involving rainfall totals",
                source="test",
                content_embedding=_unit_vector(1),
            )
        )

        # Deliberately zero shared vocabulary with the stored content above.
        text_only_results = await repository.search_text(
            "ns", "who is employed there currently", limit=10
        )
        hybrid_results = await repository.search_hybrid(
            "ns", "who is employed there currently", _unit_vector(0), limit=10
        )

        assert semantic_match.id not in [r.record.id for r in text_only_results]
        assert hybrid_results[0].record.id == semantic_match.id

    async def test_search_hybrid_excludes_zero_score_results(
        self, repository: MemoryRepository
    ) -> None:
        await repository.create(
            NewMemory(namespace="ns", content="totally unrelated", source="test")
        )

        results = await repository.search_hybrid("ns", "nomatch", _unit_vector(0), limit=10)

        assert results == []

    async def test_count_unconsolidated_counts_only_unmarked_active_memories(
        self, repository: MemoryRepository
    ) -> None:
        await repository.create(NewMemory(namespace="ns", content="a", source="test"))
        await repository.create(NewMemory(namespace="ns", content="b", source="test"))
        deleted = await repository.create(NewMemory(namespace="ns", content="c", source="test"))
        await repository.soft_delete(deleted.id, reason=None)

        assert await repository.count_unconsolidated("ns") == 2
        assert await repository.count_unconsolidated("ns-other") == 0

    async def test_list_unconsolidated_respects_limit_and_oldest_first(
        self, repository: MemoryRepository
    ) -> None:
        first = await repository.create(NewMemory(namespace="ns", content="first", source="test"))
        await repository.create(NewMemory(namespace="ns", content="second", source="test"))

        results = await repository.list_unconsolidated("ns", limit=1)

        assert len(results) == 1
        assert results[0].id == first.id

    async def test_mark_consolidated_excludes_from_list_unconsolidated(
        self, repository: MemoryRepository
    ) -> None:
        created = await repository.create(NewMemory(namespace="ns", content="a", source="test"))

        await repository.mark_consolidated([created.id], datetime.now(UTC))

        assert await repository.count_unconsolidated("ns") == 0
        fetched = await repository.get_by_id("ns", created.id)
        assert fetched is not None
        assert fetched.consolidated_at is not None

    async def test_update_salience_persists_score(self, repository: MemoryRepository) -> None:
        created = await repository.create(NewMemory(namespace="ns", content="a", source="test"))
        assert created.salience_score is None

        await repository.update_salience(created.id, 0.75)

        fetched = await repository.get_by_id("ns", created.id)
        assert fetched is not None
        assert fetched.salience_score == pytest.approx(0.75)

    async def test_find_similar_pairs_finds_matches_above_threshold(
        self, repository: MemoryRepository
    ) -> None:
        a = await repository.create(
            NewMemory(namespace="ns", content="a", source="test", content_embedding=_unit_vector(0))
        )
        b = await repository.create(
            NewMemory(namespace="ns", content="b", source="test", content_embedding=_unit_vector(0))
        )
        c = await repository.create(
            NewMemory(namespace="ns", content="c", source="test", content_embedding=_unit_vector(1))
        )

        pairs = await repository.find_similar_pairs("ns", [a.id, b.id, c.id], threshold=0.99)

        matched_ids = {frozenset((x, y)) for x, y, _ in pairs}
        assert frozenset((a.id, b.id)) in matched_ids
        assert frozenset((a.id, c.id)) not in matched_ids
        assert frozenset((b.id, c.id)) not in matched_ids

    async def test_find_similar_pairs_excludes_records_without_embedding(
        self, repository: MemoryRepository
    ) -> None:
        a = await repository.create(
            NewMemory(namespace="ns", content="a", source="test", content_embedding=_unit_vector(0))
        )
        b = await repository.create(NewMemory(namespace="ns", content="b", source="test"))

        pairs = await repository.find_similar_pairs("ns", [a.id, b.id], threshold=0.0)

        assert pairs == []

    async def test_create_stores_session_outcome(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(
                namespace="ns",
                content="the fix worked",
                source="test",
                session_outcome="success",
            )
        )

        fetched = await repository.get_by_id("ns", created.id)
        assert fetched is not None
        assert fetched.session_outcome == "success"

    async def test_create_with_no_session_outcome_defaults_to_none(
        self, repository: MemoryRepository
    ) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="no outcome reported", source="test")
        )

        assert created.session_outcome is None

    async def test_new_memory_has_no_access_history(self, repository: MemoryRepository) -> None:
        created = await repository.create(
            NewMemory(namespace="ns", content="never read", source="test")
        )

        assert created.last_accessed_at is None
        assert created.access_count == 0

    async def test_record_access_updates_timestamp_and_increments_count(
        self, repository: MemoryRepository
    ) -> None:
        from datetime import UTC, datetime

        created = await repository.create(
            NewMemory(namespace="ns", content="read me twice", source="test")
        )
        first = datetime(2026, 9, 1, tzinfo=UTC)
        second = datetime(2026, 9, 2, tzinfo=UTC)

        await repository.record_access([created.id], first)
        await repository.record_access([created.id], second)

        fetched = await repository.get_by_id("ns", created.id)
        assert fetched is not None
        assert fetched.access_count == 2
        assert fetched.last_accessed_at == second

    async def test_record_access_ignores_deleted_unknown_and_empty(
        self, repository: MemoryRepository
    ) -> None:
        from datetime import UTC, datetime

        created = await repository.create(
            NewMemory(namespace="ns", content="to be forgotten", source="test")
        )
        await repository.soft_delete(created.id, reason="test")

        await repository.record_access([created.id, "not-a-uuid"], datetime(2026, 9, 1, tzinfo=UTC))
        await repository.record_access([], datetime(2026, 9, 1, tzinfo=UTC))

        assert await repository.get_by_id("ns", created.id) is None
