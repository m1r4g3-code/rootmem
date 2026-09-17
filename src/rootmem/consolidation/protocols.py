"""The distillation port: `DistillationProvider`.

Sibling to `EmbeddingProvider`/`ExtractionProvider` (ADR 0009's Protocol
pattern), not a reuse of `ExtractionProvider` itself: the input shape
differs (a cluster of episode texts, not one passage), even though the
output type is reused directly (`ExtractionResult` — distillation produces
the same entities/relations-by-name shape as extraction, just abstracted
across several source episodes instead of derived from one).
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from rootmem.extraction.models import ExtractionResult


class DistillationError(Exception):
    """Raised when the distillation provider is unreachable, rejects a
    request, or returns output that doesn't parse into `ExtractionResult`."""


class DistillationContext(BaseModel):
    namespace: str


class DistillationProvider(Protocol):
    async def distill(self, texts: list[str], context: DistillationContext) -> ExtractionResult:
        """Abstract a durable semantic fact from a cluster of near-duplicate
        episode texts (ADR 0015's clustering output). Raises
        `DistillationError` on failure — never returns a partial result
        silently."""
        ...
