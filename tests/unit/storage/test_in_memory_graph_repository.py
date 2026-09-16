from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.graph_models import NewEntity
from tests.unit.storage.graph_contract import GraphRepositoryContract


class TestInMemoryGraphRepository(GraphRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryGraphRepository:
        return InMemoryGraphRepository(contradiction_confidence_floor=0.5)


@pytest.mark.asyncio
async def test_link_memory_entity_is_idempotent() -> None:
    """Not in the shared contract: the real Postgres implementation
    enforces a foreign key from memory_entities.memory_id to memories(id),
    which the shared GraphRepositoryContract fixture has no memories row to
    satisfy — see tests/integration/test_postgres_graph_roundtrip.py for the
    Postgres-specific version of this test with a real memory row."""
    repository = InMemoryGraphRepository()
    entity = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Person", name="Alice")
    )

    await repository.link_memory_entity("11111111-1111-1111-1111-111111111111", entity.id)
    await repository.link_memory_entity("11111111-1111-1111-1111-111111111111", entity.id)
