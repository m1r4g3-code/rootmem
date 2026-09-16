"""Real calls to the live Anthropic API — costs money per run (NFR6), so
this is marked `integration_external` (see
tests/integration/test_voyage_embedding_provider.py's module docstring for
why that's a separate marker from the free Docker-only `integration` job).

Requires ANTHROPIC_API_KEY set (see .env).
"""

from __future__ import annotations

import pytest

from rootmem.config import get_settings
from rootmem.extraction.anthropic_provider import AnthropicExtractionProvider
from rootmem.extraction.models import ExtractionContext


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_extracts_entity_and_relation_from_plain_sentence() -> None:
    settings = get_settings()
    provider = AnthropicExtractionProvider(settings)
    context = ExtractionContext(namespace="ns", source="test")

    result = await provider.extract("Alice works at Acme Corp.", context)

    entity_names = {e.name.lower() for e in result.entities}
    assert any("alice" in name for name in entity_names)
    assert any("acme" in name for name in entity_names)

    assert len(result.relations) >= 1
    relation = result.relations[0]
    assert "alice" in relation.subject_name.lower()
    assert relation.object_name is not None
    assert "acme" in relation.object_name.lower()


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_extracts_contradicting_relation_from_second_sentence() -> None:
    """The exit criterion's actual extraction step: two independently
    extracted sentences about the same subject+predicate should each
    resolve to compatible subject names/types, so the pipeline's entity
    resolution (exact normalized-name match) can recognize them as the
    same entity downstream."""
    settings = get_settings()
    provider = AnthropicExtractionProvider(settings)
    context = ExtractionContext(namespace="ns", source="test")

    first = await provider.extract("Alice works at Acme Corp.", context)
    second = await provider.extract("Alice joined Globex as an engineer.", context)

    first_relation = first.relations[0]
    second_relation = second.relations[0]
    assert first_relation.predicate == second_relation.predicate == "works_at"
    assert first_relation.subject_name.lower() == second_relation.subject_name.lower()
    assert first_relation.object_name != second_relation.object_name
