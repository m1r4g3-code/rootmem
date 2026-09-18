"""Real calls to the live Anthropic API — costs money per run (NFR6), same
marker rationale as tests/integration/test_anthropic_extraction_provider.py.

Requires ANTHROPIC_API_KEY set (see .env).
"""

from __future__ import annotations

import pytest

from rootmem.config import get_settings
from rootmem.consolidation.anthropic_distillation_provider import AnthropicDistillationProvider
from rootmem.consolidation.protocols import DistillationContext


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_distills_near_duplicate_restatements_into_one_fact() -> None:
    settings = get_settings()
    provider = AnthropicDistillationProvider(settings)
    context = DistillationContext(namespace="ns")

    result = await provider.distill(
        [
            "Alice works at Acme Corp.",
            "Alice is employed at Acme Corp.",
            "Alice's employer is Acme Corp.",
        ],
        context,
    )

    entity_names = {e.name.lower() for e in result.entities}
    assert any("alice" in name for name in entity_names)
    assert any("acme" in name for name in entity_names)

    # Exactly one durable fact, not one record per passage.
    assert len(result.relations) == 1
    relation = result.relations[0]
    assert "alice" in relation.subject_name.lower()
    assert relation.predicate == "works_at"
    assert relation.object_name is not None
    assert "acme" in relation.object_name.lower()
    # Corroborated by three independent restatements -- confidence should
    # reflect that, per the distillation system prompt's own instruction.
    assert relation.confidence >= 0.9
