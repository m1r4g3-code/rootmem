"""Scripted `ProceduralDistillationProvider` fake — returns pre-registered
`SkillDraft`s keyed by the exact set of input traces, order-independent.
Same rationale as `ScriptedDistillationProvider`/
`ScriptedExtractionProvider` for why a lookup table, not fixture-replay, is
the right fake here.
"""

from __future__ import annotations

from rootmem.consolidation.procedural_protocols import (
    ProceduralDistillationContext,
    ProceduralDistillationError,
    SkillDraft,
)


def _key(traces: list[list[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(tuple(trace) for trace in traces))


class ScriptedProceduralDistillationProvider:
    def __init__(self) -> None:
        self._scripted: dict[tuple[tuple[str, ...], ...], SkillDraft] = {}

    def register(self, traces: list[list[str]], draft: SkillDraft) -> None:
        self._scripted[_key(traces)] = draft

    async def distill_procedure(
        self, traces: list[list[str]], context: ProceduralDistillationContext
    ) -> SkillDraft:
        key = _key(traces)
        if key not in self._scripted:
            raise ProceduralDistillationError(
                f"ScriptedProceduralDistillationProvider has no registered draft for: {traces!r} "
                "— call .register(traces, draft) before using it in a test"
            )
        return self._scripted[key]
