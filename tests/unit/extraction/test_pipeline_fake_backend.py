"""Tests `extraction.pipeline.apply_extraction` against
`InMemoryGraphRepository` — the orchestration logic (name resolution,
memory_entities linking), not the contradiction rule itself (already fully
covered by tests/unit/storage/graph_contract.py, since that rule lives in
`GraphRepository.create_relation`, not here)."""

from __future__ import annotations

import pytest

from rootmem.extraction.models import ExtractedEntity, ExtractedRelation, ExtractionResult
from rootmem.extraction.pipeline import apply_extraction
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository


@pytest.mark.asyncio
async def test_creates_entities_and_relation_with_resolved_ids() -> None:
    graph = InMemoryGraphRepository()
    result = ExtractionResult(
        entities=[
            ExtractedEntity(name="Alice", entity_type="Person"),
            ExtractedEntity(name="Acme Corp", entity_type="Organization"),
        ],
        relations=[
            ExtractedRelation(
                subject_name="Alice",
                subject_type="Person",
                predicate="works_at",
                object_name="Acme Corp",
                object_type="Organization",
            )
        ],
    )

    apply_result = await apply_extraction(graph, "ns", result)

    assert len(apply_result.resolutions) == 1
    alice = await graph.find_entity_by_name("ns", "Person", "Alice")
    acme = await graph.find_entity_by_name("ns", "Organization", "Acme Corp")
    assert alice is not None and acme is not None
    assert apply_result.resolutions[0].new.subject_entity_id == alice.id
    assert apply_result.resolutions[0].new.object_entity_id == acme.id
    assert set(apply_result.entity_ids) == {alice.id, acme.id}


@pytest.mark.asyncio
async def test_resolves_entities_not_explicitly_listed() -> None:
    """An extraction result whose `relations` mention a subject/object that
    isn't also in `entities` (a real LLM won't always list every entity
    separately) still resolves correctly — the pipeline must not assume
    every relation's endpoints were pre-declared."""
    graph = InMemoryGraphRepository()
    result = ExtractionResult(
        relations=[
            ExtractedRelation(
                subject_name="Bob",
                subject_type="Person",
                predicate="works_at",
                object_name="Globex",
                object_type="Organization",
            )
        ]
    )

    apply_result = await apply_extraction(graph, "ns", result)

    assert len(apply_result.resolutions) == 1
    bob = await graph.find_entity_by_name("ns", "Person", "Bob")
    assert bob is not None
    assert apply_result.resolutions[0].new.subject_entity_id == bob.id


@pytest.mark.asyncio
async def test_applies_contradiction_rule_across_two_extraction_calls() -> None:
    """The exit criterion's shape, at the pipeline level: two separate
    extraction results, same (subject, predicate), different object —
    the second call's relation must supersede the first's."""
    graph = InMemoryGraphRepository(contradiction_confidence_floor=0.5)
    first_result = ExtractionResult(
        relations=[
            ExtractedRelation(
                subject_name="Alice",
                subject_type="Person",
                predicate="works_at",
                object_name="Acme Corp",
                object_type="Organization",
            )
        ]
    )
    second_result = ExtractionResult(
        relations=[
            ExtractedRelation(
                subject_name="Alice",
                subject_type="Person",
                predicate="works_at",
                object_name="Globex",
                object_type="Organization",
            )
        ]
    )

    first_apply = await apply_extraction(graph, "ns", first_result)
    second_apply = await apply_extraction(graph, "ns", second_result)
    second_resolutions = second_apply.resolutions

    assert second_resolutions[0].previous is not None
    assert second_resolutions[0].previous.id == first_apply.resolutions[0].new.id
    assert second_resolutions[0].previous.valid_to is not None
    assert second_resolutions[0].new.is_active


@pytest.mark.asyncio
async def test_links_all_resolved_entities_to_source_memory() -> None:
    graph = InMemoryGraphRepository()
    result = ExtractionResult(
        relations=[
            ExtractedRelation(
                subject_name="Alice",
                subject_type="Person",
                predicate="works_at",
                object_name="Acme Corp",
                object_type="Organization",
            )
        ]
    )

    await apply_extraction(graph, "ns", result, source_memory_id="mem-1")

    alice = await graph.find_entity_by_name("ns", "Person", "Alice")
    assert alice is not None
    assert ("mem-1", alice.id) in graph.memory_entity_links
