"""Shared behavioral contract for every `ConsolidationRepository` implementation.

Both `InMemoryConsolidationRepository` and `PostgresConsolidationRepository`
are run against this same suite — exact parity with the
`MemoryRepositoryContract`/`GraphRepositoryContract` pattern.

This module is a base class, not a test file itself (no `test_` prefix), so
pytest doesn't try to collect it directly.
"""

from __future__ import annotations

import pytest

from rootmem.storage.consolidation_protocols import ConsolidationRepository
from rootmem.storage.protocols import NotFoundError


class ConsolidationRepositoryContract:
    """Subclass and provide an async `repository` fixture yielding a fresh
    `ConsolidationRepository` for each test."""

    @pytest.fixture
    def repository(self) -> ConsolidationRepository:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    async def test_get_last_run_with_no_prior_run_returns_none(
        self, repository: ConsolidationRepository
    ) -> None:
        assert await repository.get_last_run("ns") is None

    async def test_start_run_records_trigger_reason_and_started_state(
        self, repository: ConsolidationRepository
    ) -> None:
        run = await repository.start_run("ns", "count")

        assert run.namespace == "ns"
        assert run.trigger_reason == "count"
        assert run.completed_at is None
        assert run.episodes_processed == 0
        assert run.clusters_formed == 0
        assert run.facts_distilled == 0

    async def test_complete_run_records_outcome_counts(
        self, repository: ConsolidationRepository
    ) -> None:
        run = await repository.start_run("ns", "manual")

        completed = await repository.complete_run(
            run.id, episodes_processed=10, clusters_formed=3, facts_distilled=2
        )

        assert completed.id == run.id
        assert completed.completed_at is not None
        assert completed.episodes_processed == 10
        assert completed.clusters_formed == 3
        assert completed.facts_distilled == 2
        assert completed.procedures_distilled == 0
        assert completed.lessons_distilled == 0

    async def test_complete_run_records_procedural_and_lesson_counts(
        self, repository: ConsolidationRepository
    ) -> None:
        run = await repository.start_run("ns", "manual")

        completed = await repository.complete_run(
            run.id,
            episodes_processed=6,
            clusters_formed=1,
            facts_distilled=1,
            procedures_distilled=1,
            lessons_distilled=1,
        )

        assert completed.procedures_distilled == 1
        assert completed.lessons_distilled == 1

    async def test_complete_run_missing_raises_not_found(
        self, repository: ConsolidationRepository
    ) -> None:
        with pytest.raises(NotFoundError):
            await repository.complete_run(
                "00000000-0000-0000-0000-000000000000",
                episodes_processed=0,
                clusters_formed=0,
                facts_distilled=0,
            )

    async def test_get_last_run_returns_most_recently_started(
        self, repository: ConsolidationRepository
    ) -> None:
        first = await repository.start_run("ns", "time")
        second = await repository.start_run("ns", "count")

        last = await repository.get_last_run("ns")

        assert last is not None
        assert last.id == second.id
        assert last.id != first.id

    async def test_get_last_run_respects_namespace(
        self, repository: ConsolidationRepository
    ) -> None:
        await repository.start_run("ns-a", "manual")

        assert await repository.get_last_run("ns-b") is None
