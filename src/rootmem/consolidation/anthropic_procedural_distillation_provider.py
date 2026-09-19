"""`anthropic`-backed `ProceduralDistillationProvider`. Haiku-tier, per ADR
0009's precedent — structured output via tool-calling, same mechanism as
`AnthropicDistillationProvider`, but a distinct system prompt oriented at
abstracting a named, reusable procedure (or a cautionary lesson) from
ordered session traces rather than a single durable fact from near-duplicate
restatements.
"""

from __future__ import annotations

from typing import Any

import anthropic
import pydantic

from rootmem.config import Settings
from rootmem.consolidation.procedural_protocols import (
    ProceduralDistillationContext,
    ProceduralDistillationError,
)
from rootmem.consolidation.skill_format import SkillDraft

_TOOL_NAME = "record_skill"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": (
        "Record a single named, reusable procedure or lesson abstracted "
        "from one or more ordered session traces."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A short, lowercase, hyphen-separated slug identifying "
                    "this procedure or lesson, e.g. 'fix-missing-config-default'."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "One to two sentences stating what this procedure/lesson "
                    "is AND when to use it -- both are required."
                ),
            },
            "body_markdown": {
                "type": "string",
                "description": (
                    "The full guidance as markdown: for a skill, a numbered "
                    "step list generalized across the given traces (not "
                    "copied verbatim from just one); for a lesson, a "
                    "description of what went wrong and what to avoid."
                ),
            },
        },
        "required": ["name", "description", "body_markdown"],
    },
}

_SKILL_SYSTEM_PROMPT = (
    "You will be given two or more session traces, each an ordered sequence "
    "of steps describing an attempt at a task, all of which succeeded. They "
    "were grouped together because they represent the same underlying "
    "procedure carried out in different words. Abstract the ONE reusable "
    "procedure they all demonstrate into a short, generalized, numbered step "
    "list -- do not copy any single trace verbatim, and do not include "
    "details specific to only one trace (e.g. one trace's exact error "
    "message) unless every trace shares it. Give it a short, memorable, "
    "lowercase, hyphen-separated name and a description stating both what it "
    "does and when to use it."
)

_LESSON_SYSTEM_PROMPT = (
    "You will be given exactly one session trace, an ordered sequence of "
    "steps describing a failed attempt at a task. Distill a short, concrete "
    "lesson from it: what the proximate cause of the failure was, and what "
    "to avoid or check next time. Give it a short, memorable, lowercase, "
    "hyphen-separated name and a description stating both what this lesson "
    "warns against and when it applies."
)


class AnthropicProceduralDistillationProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ProceduralDistillationError("ANTHROPIC_API_KEY is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.procedural_distillation_model_or_default
        self._max_tokens = settings.extraction_max_tokens_per_call

    async def distill_procedure(
        self, traces: list[list[str]], context: ProceduralDistillationContext
    ) -> SkillDraft:
        system_prompt = _SKILL_SYSTEM_PROMPT if context.kind == "skill" else _LESSON_SYSTEM_PROMPT
        combined = "\n\n".join(
            f"Trace {i + 1}:\n" + "\n".join(f"  {j + 1}. {step}" for j, step in enumerate(trace))
            for i, trace in enumerate(traces)
        )
        try:
            message = await self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=self._max_tokens,
                system=system_prompt,
                tools=[_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": combined}],
            )
        except anthropic.APIError as exc:
            raise ProceduralDistillationError(
                f"Anthropic procedural distillation request failed: {exc}"
            ) from exc

        tool_use = next((block for block in message.content if block.type == "tool_use"), None)
        if tool_use is None:
            raise ProceduralDistillationError("Anthropic response contained no tool_use block")

        try:
            return SkillDraft.model_validate(tool_use.input)
        except pydantic.ValidationError as exc:
            raise ProceduralDistillationError(
                f"procedural distillation tool output failed validation: {exc}"
            ) from exc
