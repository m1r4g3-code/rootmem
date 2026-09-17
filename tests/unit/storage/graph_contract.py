"""Shared behavioral contract for every `GraphRepository` implementation.

Both `InMemoryGraphRepository` and `PostgresGraphRepository` are run against
this same suite (see test_in_memory_graph_repository.py and
tests/integration/test_postgres_graph_roundtrip.py) — exact parity with the
`MemoryRepositoryContract`/`contract.py` pattern.

This module is a base class, not a test file itself (no `test_` prefix), so
pytest doesn't try to collect it directly.
"""

from __future__ import annotations

import pytest

from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.graph_protocols import GraphRepository


class GraphRepositoryContract:
    """Subclass and provide an async `repository` fixture yielding a fresh
    `GraphRepository`, constructed with a default `BayesianSettings`
    (`extraction.contradiction`), for each test."""

    @pytest.fixture
    def repository(self) -> GraphRepository:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    async def test_upsert_entity_creates_new(self, repository: GraphRepository) -> None:
        entity = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )

        assert entity.name == "Alice"
        assert entity.canonical_key == "alice"
        # entity_type is normalized (lowercased), not preserved verbatim
        # like `name` — a real run against the live Anthropic API showed
        # entity-type casing isn't a reliable signal worth keeping around;
        # see storage/graph_normalize.py's docstring for the full story.
        assert entity.entity_type == "person"

    async def test_upsert_entity_dedupes_by_normalized_name(
        self, repository: GraphRepository
    ) -> None:
        first = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        second = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="  ALICE  ")
        )

        assert second.id == first.id

    async def test_upsert_entity_scoped_by_type_and_namespace(
        self, repository: GraphRepository
    ) -> None:
        person = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Acme")
        )
        org = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )
        other_ns = await repository.upsert_entity(
            NewEntity(namespace="ns-2", entity_type="Person", name="Acme")
        )

        assert len({person.id, org.id, other_ns.id}) == 3

    async def test_get_entity_by_id_wrong_namespace_returns_none(
        self, repository: GraphRepository
    ) -> None:
        entity = await repository.upsert_entity(
            NewEntity(namespace="ns-a", entity_type="Person", name="Alice")
        )

        assert await repository.get_entity_by_id("ns-b", entity.id) is None

    async def test_find_entity_by_name_missing_returns_none(
        self, repository: GraphRepository
    ) -> None:
        assert await repository.find_entity_by_name("ns", "Person", "Nobody") is None

    async def test_create_relation_with_no_prior_is_simply_active(
        self, repository: GraphRepository
    ) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )

        resolution = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=1.0,
            )
        )

        assert resolution.previous is None
        assert resolution.contested is False
        assert resolution.new.is_active
        assert resolution.new.supersedes is None

    async def test_create_relation_supersedes_prior_when_confident(
        self, repository: GraphRepository
    ) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )
        globex = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Globex")
        )

        first = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=0.6,
            )
        )
        second = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=globex.id,
                confidence=1.0,
            )
        )

        assert second.contested is False
        assert second.new.supersedes == first.new.id
        assert second.previous is not None
        assert second.previous.id == first.new.id
        assert second.previous.superseded_by == second.new.id
        assert second.previous.valid_to is not None
        assert second.new.is_active

    async def test_create_relation_marks_contested_when_low_confidence(
        self, repository: GraphRepository
    ) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )
        globex = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Globex")
        )

        first = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=1.0,
            )
        )
        second = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=globex.id,
                confidence=0.1,
            )
        )

        assert second.contested is True
        assert second.new.is_contested
        assert second.new.is_active
        assert second.new.supersedes is None
        assert second.previous is not None
        assert second.previous.id == first.new.id
        assert second.previous.is_contested
        assert second.previous.is_active  # not superseded — both remain active

    async def test_related_returns_relations_touching_entity(
        self, repository: GraphRepository
    ) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )
        bob = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Bob")
        )

        await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
            )
        )
        await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=bob.id,
                predicate="works_at",
                object_entity_id=acme.id,
            )
        )

        alice_relations = await repository.related("ns", alice.id, max_hops=1)

        assert len(alice_relations) == 1
        assert alice_relations[0].subject_entity_id == alice.id

    async def test_related_includes_superseded_relations(self, repository: GraphRepository) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )
        globex = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Globex")
        )

        await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=0.6,
            )
        )
        await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=globex.id,
                confidence=1.0,
            )
        )

        relations = await repository.related("ns", alice.id, max_hops=1)

        assert len(relations) == 2
        active = [r for r in relations if r.is_active]
        superseded = [r for r in relations if not r.is_active]
        assert len(active) == 1
        assert len(superseded) == 1
        assert active[0].object_entity_id == globex.id
        assert superseded[0].object_entity_id == acme.id
        assert superseded[0].valid_to is not None

    async def test_create_relation_corroborates_identical_restatement(
        self, repository: GraphRepository
    ) -> None:
        """ADR 0013's closed Phase 1 gap: restating the same fact should
        strengthen it, not silently supersede it with an indistinguishable
        copy."""
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )
        acme = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Organization", name="Acme")
        )

        first = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=0.9,
            )
        )
        second = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=0.9,
            )
        )

        assert second.corroborated is True
        assert second.contested is False
        assert second.previous is None
        # No new row -- the same relation, strengthened.
        assert second.new.id == first.new.id
        assert second.new.confidence > first.new.confidence

        relations = await repository.related("ns", alice.id, max_hops=1)
        assert len(relations) == 1

    async def test_create_relation_corroboration_extends_to_literal_objects(
        self, repository: GraphRepository
    ) -> None:
        alice = await repository.upsert_entity(
            NewEntity(namespace="ns", entity_type="Person", name="Alice")
        )

        first = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="favorite_color",
                object_literal="blue",
                confidence=0.9,
            )
        )
        second = await repository.create_relation(
            NewRelation(
                namespace="ns",
                subject_entity_id=alice.id,
                predicate="favorite_color",
                object_literal="blue",
                confidence=0.9,
            )
        )

        assert second.corroborated is True
        assert second.new.id == first.new.id

    # `link_relation_provenance`/`get_relation_provenance` are NOT in this
    # shared contract: the real Postgres implementation enforces a foreign
    # key from relation_provenance.memory_id to memories(id) (mirroring
    # memory_entities' own FK), which this fixture has no memories row to
    # satisfy -- see test_in_memory_graph_repository.py and
    # tests/integration/test_postgres_graph_roundtrip.py for the two
    # implementation-specific versions of this test, same pattern as
    # link_memory_entity's own idempotency test.

    async def test_record_feedback_confirmed_raises_confidence(
        self, repository: GraphRepository
    ) -> None:
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
                    confidence=0.9,
                )
            )
        ).new

        updated = await repository.record_feedback(
            "ns", relation.id, outcome="confirmed", reported_confidence=1.0, note="looks right"
        )

        assert updated.confidence > relation.confidence

    async def test_record_feedback_contradicted_lowers_confidence(
        self, repository: GraphRepository
    ) -> None:
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
                    confidence=0.9,
                )
            )
        ).new

        updated = await repository.record_feedback(
            "ns", relation.id, outcome="contradicted", reported_confidence=1.0, note=None
        )

        assert updated.confidence < relation.confidence

    async def test_record_feedback_missing_relation_raises_not_found(
        self, repository: GraphRepository
    ) -> None:
        from rootmem.storage.graph_protocols import NotFoundError

        with pytest.raises(NotFoundError):
            await repository.record_feedback(
                "ns",
                "00000000-0000-0000-0000-000000000000",
                outcome="confirmed",
                reported_confidence=1.0,
                note=None,
            )

    async def test_related_respects_namespace(self, repository: GraphRepository) -> None:
        alice_a = await repository.upsert_entity(
            NewEntity(namespace="ns-a", entity_type="Person", name="Alice")
        )
        acme_a = await repository.upsert_entity(
            NewEntity(namespace="ns-a", entity_type="Organization", name="Acme")
        )
        await repository.create_relation(
            NewRelation(
                namespace="ns-a",
                subject_entity_id=alice_a.id,
                predicate="works_at",
                object_entity_id=acme_a.id,
            )
        )

        relations = await repository.related("ns-b", alice_a.id, max_hops=1)

        assert relations == []
