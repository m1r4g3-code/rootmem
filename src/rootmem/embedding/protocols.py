"""The embedding port: `EmbeddingProvider`.

A separate Protocol from anything in `storage/` (ADR 0009) — the storage
layer never calls out to Voyage itself (charter's layer-isolation mandate,
already cited in ADR 0003). `remember`'s tool handler calls this, then
passes the resulting vector to `MemoryRepository.create` via
`NewMemory.content_embedding`.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingError(Exception):
    """Raised when the embedding provider is unreachable or rejects a
    request. Callers (the `remember` tool handler) catch this and degrade
    to `content_embedding=None` rather than failing the write — see
    docs/requirements/phase1-requirements.md FR1/NFR2."""


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, same order as `texts`.

        Raises `EmbeddingError` on failure — never returns a partial or
        padded result silently.
        """
        ...
