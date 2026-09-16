"""`anthropic`-backed `ExtractionProvider`. Haiku-tier, per ADR 0009 —
structured output via tool-calling (a single forced tool call), not
free-text parsing, so a malformed response is a clean validation error
against `ExtractionResult`'s schema rather than a brittle regex/JSON guess.
"""

from __future__ import annotations

from typing import Any

import anthropic
import pydantic

from rootmem.config import Settings
from rootmem.extraction.models import ExtractionContext, ExtractionResult
from rootmem.extraction.protocols import ExtractionError

_TOOL_NAME = "record_extraction"

_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "Record the entities and relations extracted from the given text.",
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
    "Extract entities and relations from the given text. Use snake_case "
    "predicates, and always canonicalize to the same predicate for the "
    "same underlying relationship regardless of the verb the text actually "
    "uses — e.g. 'works at', 'joined ... as', 'is employed by', and "
    "'started working at' must ALL produce the predicate works_at, not a "
    "different word per sentence. This matters: two facts about the same "
    "subject+predicate are later compared by exact predicate string to "
    "detect contradictions, so inconsistent predicate choices for the same "
    "relationship type would silently break that comparison. Prefer a "
    "small, reusable set of predicates (works_at, lives_in, married_to, "
    "located_in, member_of, etc.) over inventing a new one per sentence. "
    "If the object of a relation is a named entity, set object_name and "
    "object_type; if it's a plain value (a date, a number, a color), set "
    "object_literal instead. Set confidence lower (below 0.5) only when "
    "the text itself hedges or is ambiguous about the fact — not for "
    "ordinary declarative statements."
)


class AnthropicExtractionProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ExtractionError("ANTHROPIC_API_KEY is not configured")
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.extraction_model
        self._max_tokens = settings.extraction_max_tokens_per_call

    async def extract(self, text: str, context: ExtractionContext) -> ExtractionResult:
        try:
            # The SDK's overloads want each tool/tool_choice/message as a
            # specific TypedDict variant; a hand-built JSON-schema dict (the
            # natural shape for a tool definition) doesn't satisfy that
            # without extensive casting that buys nothing, since the real
            # API validates the actual shape at call time regardless.
            message = await self._client.messages.create(  # type: ignore[call-overload]
                model=self._model,
                max_tokens=self._max_tokens,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": text}],
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"Anthropic extraction request failed: {exc}") from exc

        tool_use = next(
            (block for block in message.content if block.type == "tool_use"), None
        )
        if tool_use is None:
            raise ExtractionError("Anthropic response contained no tool_use block")

        try:
            return ExtractionResult.model_validate(tool_use.input)
        except pydantic.ValidationError as exc:
            raise ExtractionError(f"extraction tool output failed validation: {exc}") from exc
