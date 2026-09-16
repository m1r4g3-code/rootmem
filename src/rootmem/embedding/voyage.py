"""`voyageai`-backed `EmbeddingProvider`. See ADR 0007 (model/dimension
choice) and ADR 0009 (why this Protocol exists separately from storage)."""

from __future__ import annotations

import voyageai.error
from voyageai import AsyncClient  # type: ignore[attr-defined]  # voyageai ships no py.typed marker

from rootmem.config import Settings
from rootmem.embedding.protocols import EmbeddingError


class VoyageEmbeddingProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.voyage_api_key:
            raise EmbeddingError("VOYAGE_API_KEY is not configured")
        self._client = AsyncClient(api_key=settings.voyage_api_key)
        self._model = settings.voyage_model
        self._output_dimension = settings.voyage_output_dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            result = await self._client.embed(
                texts, model=self._model, output_dimension=self._output_dimension
            )
        except voyageai.error.VoyageError as exc:
            raise EmbeddingError(f"Voyage embedding request failed: {exc}") from exc
        return [[float(x) for x in vector] for vector in result.embeddings]
