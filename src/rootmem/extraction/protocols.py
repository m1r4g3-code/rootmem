"""The extraction port: `ExtractionProvider`.

A separate Protocol from `EmbeddingProvider` (ADR 0009) — different
interface, different failure modes, different testing strategy (scripted
fake, not fixture-replay, since extraction's output is structured
entities/relations, not a vector whose "closeness" fixture-replay is suited
to validate).
"""

from __future__ import annotations

from typing import Protocol

from rootmem.extraction.models import ExtractionContext, ExtractionResult


class ExtractionError(Exception):
    """Raised when the extraction provider is unreachable, rejects a
    request, or returns output that doesn't parse into `ExtractionResult`."""


class ExtractionProvider(Protocol):
    async def extract(self, text: str, context: ExtractionContext) -> ExtractionResult:
        """Extract entities and relations from `text`. Raises
        `ExtractionError` on failure — never returns a partial result
        silently."""
        ...
