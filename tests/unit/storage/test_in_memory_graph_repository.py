from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.graph_models import NewEntity, NewRelation
from tests.unit.storage.graph_contract import GraphRepositoryContract


class TestInMemoryGraphRepository(GraphRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryGraphRepository:
        return InMemoryGraphRepository()


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


@pytest.mark.asyncio
async def test_link_relation_provenance_is_idempotent_and_readable() -> None:
    """Not in the shared contract: see test_link_memory_entity_is_idempotent
    above for why (the real Postgres implementation's foreign key to
    memories(id)) -- see tests/integration/test_postgres_graph_roundtrip.py
    for the Postgres-specific version with real memory rows."""
    repository = InMemoryGraphRepository()
    alice = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Person", name="Alice")
    )
    acme = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Acme")
    )
    relation = (
        await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
            )
        )
    ).new

    await repository.link_relation_provenance(relation.id, "memory-1")
    await repository.link_relation_provenance(relation.id, "memory-2")
    await repository.link_relation_provenance(relation.id, "memory-1")

    provenance = await repository.get_relation_provenance("ns", relation.id)
    assert sorted(provenance) == ["memory-1", "memory-2"]
