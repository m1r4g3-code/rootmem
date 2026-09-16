"""Scripted `ExtractionProvider` fake — returns pre-registered
`ExtractionResult`s keyed by exact input text. Unlike embeddings
(fixture-replay, ADR 0009), extraction's output is structured data a test
author writes directly — there's no "real recorded value" to replay, so a
simple lookup table is the right fake here, isolating pipeline/contradiction
logic from real LLM nondeterminism.
"""

from __future__ import annotations

from rootmem.extraction.models import ExtractionContext, ExtractionResult
from rootmem.extraction.protocols import ExtractionError


class ScriptedExtractionProvider:
    def __init__(self, scripted: dict[str, ExtractionResult] | None = None) -> None:
        self._scripted: dict[str, ExtractionResult] = dict(scripted) if scripted else {}

    def register(self, text: str, result: ExtractionResult) -> None:
        self._scripted[text] = result

    async def extract(self, text: str, context: ExtractionContext) -> ExtractionResult:
        if text not in self._scripted:
            raise ExtractionError(
                f"ScriptedExtractionProvider has no registered result for: {text!r} "
                "— call .register(text, result) before using it in a test"
            )
        return self._scripted[text]
