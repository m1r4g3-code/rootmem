"""Shared behavioral contract for every `ProceduralMemoryRepository`
implementation.

Both `InMemoryProceduralMemoryRepository` and
`PostgresProceduralMemoryRepository` are run against this same suite — exact
parity with the `MemoryRepositoryContract`/`GraphRepositoryContract`/
`ConsolidationRepositoryContract` pattern.

`link_provenance`/`get_provenance` are deliberately NOT covered here:
`procedural_memory_provenance.memory_id` has a real foreign key to
`memories(id)` in Postgres, so a shared test using made-up fake ids would
pass against the in-memory fake but fail against real Postgres — the same
gap already found and fixed for `relation_provenance` (see
`tests/integration/test_postgres_graph_roundtrip.py`'s
`test_link_relation_provenance_is_idempotent_and_readable`). Each
implementation's own test file covers provenance with ids appropriate to
that backend.

This module is a base class, not a test file itself (no `test_` prefix), so
pytest doesn't try to collect it directly.
"""

from __future__ import annotations

import pytest

from rootmem.storage.procedural_protocols import NewProceduralMemory, ProceduralMemoryRepository


class ProceduralMemoryRepositoryContract:
    """Subclass and provide an async `repository` fixture yielding a fresh
    `ProceduralMemoryRepository` for each test."""

    @pytest.fixture
    def repository(self) -> ProceduralMemoryRepository:  # pragma: no cover - overridden
        raise NotImplementedError

    async def test_get_by_name_with_no_row_returns_none(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        assert await repository.get_by_name("ns", "no-such-skill") is None

    async def test_create_returns_an_active_record(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        record = await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="skill",
                name="fix-missing-config-default",
                description="Use this when a test fails with a KeyError from a missing default.",
                body_markdown="1. Find the missing default.\n2. Add it.",
            )
        )

        assert record.namespace == "ns"
        assert record.kind == "skill"
        assert record.name == "fix-missing-config-default"
        assert record.derivation == "distilled"
        assert record.supersedes is None
        assert record.superseded_by is None
        assert record.is_active is True

    async def test_get_by_name_finds_the_active_record(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        created = await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="lesson",
                name="avoid-input-type-fix-for-serialization-bugs",
                description="Use this before changing an input type to fix a TypeError.",
                body_markdown="The real cause was a serialization bug, not the input type.",
            )
        )

        found = await repository.get_by_name("ns", "avoid-input-type-fix-for-serialization-bugs")

        assert found is not None
        assert found.id == created.id

    async def test_get_by_name_respects_namespace(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns-a",
                kind="skill",
                name="shared-name",
                description="d",
                body_markdown="b",
            )
        )

        assert await repository.get_by_name("ns-b", "shared-name") is None

    async def test_create_with_colliding_name_supersedes_the_prior_active_row(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        first = await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v1", body_markdown="v1"
            )
        )
        second = await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v2", body_markdown="v2"
            )
        )

        current = await repository.get_by_name("ns", "a-skill")
        assert current is not None
        assert current.id == second.id
        assert second.supersedes == first.id

        # The old row is never deleted, only marked superseded (ADR 0004's
        # soft-delete philosophy extended) -- FR9.
        old = await repository.get_by_name("ns", "a-skill")
        assert old is not None and old.id != first.id

    async def test_superseded_row_is_no_longer_returned_by_get_by_name(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v1", body_markdown="v1"
            )
        )
        second = await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v2", body_markdown="v2"
            )
        )

        found = await repository.get_by_name("ns", "a-skill")
        assert found is not None
        assert found.id == second.id

    async def test_search_hybrid_finds_by_text_content(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="skill",
                name="fix-missing-config-default",
                description="Use this when a test fails with a KeyError from a missing default.",
                body_markdown="Add the missing default value to the config loader.",
            )
        )
        await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="skill",
                name="unrelated-docker-fix",
                description="Use this when a docker build hangs due to a stale cache.",
                body_markdown="Clear the build cache and rebuild.",
            )
        )

        results = await repository.search_hybrid(
            "ns", "missing config default", None, kind="all", limit=10
        )

        assert len(results) == 1
        assert results[0].record.name == "fix-missing-config-default"

    async def test_search_hybrid_filters_by_kind(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="skill",
                name="fix-missing-config-default",
                description="config default keyerror fix",
                body_markdown="config default keyerror fix",
            )
        )
        await repository.create(
            NewProceduralMemory(
                namespace="ns",
                kind="lesson",
                name="avoid-wrong-fix-for-serialization-bugs",
                description="config default keyerror fix",
                body_markdown="config default keyerror fix",
            )
        )

        skill_results = await repository.search_hybrid(
            "ns", "config default keyerror fix", None, kind="skill", limit=10
        )
        lesson_results = await repository.search_hybrid(
            "ns", "config default keyerror fix", None, kind="lesson", limit=10
        )

        assert {r.record.kind for r in skill_results} == {"skill"}
        assert {r.record.kind for r in lesson_results} == {"lesson"}

    async def test_search_hybrid_respects_namespace(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns-a",
                kind="skill",
                name="a-skill",
                description="config default keyerror fix",
                body_markdown="config default keyerror fix",
            )
        )

        results = await repository.search_hybrid(
            "ns-b", "config default keyerror fix", None, kind="all", limit=10
        )
        assert results == []

    async def test_search_hybrid_excludes_superseded_rows(
        self, repository: ProceduralMemoryRepository
    ) -> None:
        await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v1", body_markdown="v1"
            )
        )
        await repository.create(
            NewProceduralMemory(
                namespace="ns", kind="skill", name="a-skill", description="v2", body_markdown="v2"
            )
        )

        results = await repository.search_hybrid("ns", "v1", None, kind="all", limit=10)
        assert results == []
