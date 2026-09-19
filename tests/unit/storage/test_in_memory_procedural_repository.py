from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.procedural_protocols import NewProceduralMemory
from tests.unit.storage.procedural_contract import ProceduralMemoryRepositoryContract


class TestInMemoryProceduralMemoryRepository(ProceduralMemoryRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryProceduralMemoryRepository:
        return InMemoryProceduralMemoryRepository()


async def test_link_provenance_is_idempotent_and_readable() -> None:
    repository = InMemoryProceduralMemoryRepository()
    record = await repository.create(
        NewProceduralMemory(
            namespace="ns", kind="skill", name="a-skill", description="d", body_markdown="b"
        )
    )

    await repository.link_provenance(record.id, "memory-1")
    await repository.link_provenance(record.id, "memory-2")
    # Idempotent -- linking the same pair twice is a no-op.
    await repository.link_provenance(record.id, "memory-1")

    provenance = await repository.get_provenance("ns", record.id)
    assert sorted(provenance) == ["memory-1", "memory-2"]


async def test_get_provenance_for_unknown_id_returns_empty() -> None:
    repository = InMemoryProceduralMemoryRepository()
    assert await repository.get_provenance("ns", "no-such-id") == []
