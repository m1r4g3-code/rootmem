"""Real calls to the live Anthropic API — costs money per run (NFR6/NFR7),
same marker rationale as tests/integration/test_anthropic_distillation_provider.py.

Requires ANTHROPIC_API_KEY set (see .env).
"""

from __future__ import annotations

import pytest

from rootmem.config import get_settings
from rootmem.consolidation.anthropic_procedural_distillation_provider import (
    AnthropicProceduralDistillationProvider,
)
from rootmem.consolidation.procedural_protocols import ProceduralDistillationContext
from rootmem.consolidation.skill_format import validate_skill_description, validate_skill_name

_TRACE_SUCCESS_A_STEPS = [
    "The test suite fails with a KeyError in the payment module.",
    "The root cause is a missing default value in the config loader.",
    "The fix is to add a default value in the config loader, and the tests pass.",
]
_TRACE_SUCCESS_B_STEPS = [
    "A test is failing due to a KeyError inside payment processing.",
    "Root cause: the config loader has no default value set.",
    "Fix applied: added a default value to the config loader; tests now pass.",
]
_TRACE_FAILURE_C_STEPS = [
    "The test suite fails with a TypeError in the billing module.",
    "Attempted fix: changed the input type in the billing handler.",
    "The fix did not work; the TypeError persisted because the root cause "
    "was actually a serialization bug in the API layer, not the input type.",
]


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_distills_two_successful_traces_into_one_generalized_skill() -> None:
    settings = get_settings()
    provider = AnthropicProceduralDistillationProvider(settings)
    context = ProceduralDistillationContext(namespace="ns", kind="skill")

    draft = await provider.distill_procedure(
        [_TRACE_SUCCESS_A_STEPS, _TRACE_SUCCESS_B_STEPS], context
    )

    # A well-formed draft, conformant with the published SKILL.md spec --
    # this is the same validation `consolidation/distill.py` applies before
    # ever persisting a real skill (NFR10).
    validate_skill_name(draft.name, max_length=settings.skill_name_max_length)
    validate_skill_description(draft.description, max_length=settings.skill_description_max_length)
    assert draft.body_markdown.strip() != ""
    # The abstraction should generalize the shared theme (a missing config
    # default causing a KeyError), not copy one trace's exact wording.
    lowered = (draft.name + " " + draft.description + " " + draft.body_markdown).lower()
    assert "default" in lowered or "config" in lowered


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_distills_a_single_failed_trace_into_a_lesson() -> None:
    settings = get_settings()
    provider = AnthropicProceduralDistillationProvider(settings)
    context = ProceduralDistillationContext(namespace="ns", kind="lesson")

    draft = await provider.distill_procedure([_TRACE_FAILURE_C_STEPS], context)

    validate_skill_name(draft.name, max_length=settings.skill_name_max_length)
    validate_skill_description(draft.description, max_length=settings.skill_description_max_length)
    assert draft.body_markdown.strip() != ""
    lowered = (draft.name + " " + draft.description + " " + draft.body_markdown).lower()
    # The lesson's proximate cause (a serialization bug, not the input type)
    # should be reflected, not the surface-level attempted (wrong) fix alone.
    assert "serializ" in lowered or "input type" in lowered
