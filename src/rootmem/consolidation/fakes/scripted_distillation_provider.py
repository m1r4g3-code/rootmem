"""Scripted `DistillationProvider` fake — returns pre-registered
`ExtractionResult`s keyed by the exact set of input texts, order-independent
(a cluster's `distill()` call always passes the same texts, but not
necessarily in the same order). Same rationale as
`extraction.fakes.scripted_provider.ScriptedExtractionProvider` for why a
lookup table, not fixture-replay, is the right fake here.
"""

from __future__ import annotations

from rootmem.consolidation.protocols import DistillationContext, DistillationError
from rootmem.extraction.models import ExtractionResult


def _key(texts: list[str]) -> tuple[str, ...]:
    return tuple(sorted(texts))


class ScriptedDistillationProvider:
    def __init__(self) -> None:
        self._scripted: dict[tuple[str, ...], ExtractionResult] = {}

    def register(self, texts: list[str], result: ExtractionResult) -> None:
        self._scripted[_key(texts)] = result

    async def distill(self, texts: list[str], context: DistillationContext) -> ExtractionResult:
        key = _key(texts)
        if key not in self._scripted:
            raise DistillationError(
                f"ScriptedDistillationProvider has no registered result for: {texts!r} "
                "— call .register(texts, result) before using it in a test"
            )
        return self._scripted[key]
