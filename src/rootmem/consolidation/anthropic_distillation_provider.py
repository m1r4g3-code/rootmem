"""`anthropic`-backed `DistillationProvider`. Haiku-tier, per ADR 0009's
precedent — structured output via tool-calling, same mechanism as
`extraction.anthropic_provider.AnthropicExtractionProvider`, but a distinct
system prompt oriented at cross-episode abstraction (summarizing a cluster
of near-duplicate restatements into one durable fact) rather than
single-passage extraction.
"""

from __future__ import annotations

from typing import Any

import anthropic
import pydantic

from rootmem.config import Settings
from rootmem.consolidation.protocols import DistillationContext, DistillationError
from rootmem.extraction.models import ExtractionResult

_TOOL_NAME = "record_distillation"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": (
        "Record the single durable fact abstracted from a cluster of "
        "near-duplicate restatements of the same underlying information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "entity_type": {"type": "string"},
                    },
                    "required": ["name", "entity_type"],
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subject_name": {"type": "string"},
                        "subject_type": {"type": "string"},
                        "predicate": {"type": "string"},
                        "object_name": {"type": "string"},
                        "object_type": {"type": "string"},
                        "object_literal": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["subject_name", "subject_type", "predicate"],
                },
            },
        },
        "required": ["entities", "relations"],
    },
}

_SYSTEM_PROMPT = (
    "You will be given several passages that all restate the same "
    "underlying fact in different words (they were clustered together "
    "because they are near-duplicates of each other, not because they are "
    "merely related). Extract exactly the ONE durable fact they all agree "
    "on, abstracted into a single, canonical entity/relation record -- do "
    "not extract separate records per passage, and do not include details "
    "that only some passages mention. Use the same snake_case predicate "
    "canonicalization discipline as single-passage extraction (e.g. "
    "'works at', 'is employed by', and 'started working at' must ALL "
    "produce works_at). Use a small, consistent, singular, capitalized "
    "vocabulary for entity types. Since this fact is corroborated by "
    "multiple independent restatements, set confidence high (0.9 or above) "
    "unless the passages actually disagree on a material detail, in which "
    "case lower it to reflect that residual uncertainty."
)


class AnthropicDistillationProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise DistillationError("ANTHROPIC_API_KEY is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.distillation_model_or_default
        self._max_tokens = settings.extraction_max_tokens_per_call

    async def distill(self, texts: list[str], context: DistillationContext) -> ExtractionResult:
        combined = "\n\n".join(f"Passage {i + 1}: {text}" for i, text in enumerate(texts))
        try:
            message = await self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": combined}],
            )
        except anthropic.APIError as exc:
            raise DistillationError(f"Anthropic distillation request failed: {exc}") from exc

        tool_use = next((block for block in message.content if block.type == "tool_use"), None)
        if tool_use is None:
            raise DistillationError("Anthropic response contained no tool_use block")

        try:
            return ExtractionResult.model_validate(tool_use.input)
        except pydantic.ValidationError as exc:
            raise DistillationError(f"distillation tool output failed validation: {exc}") from exc
