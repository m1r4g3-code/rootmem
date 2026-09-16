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
        # max_retries defaults to 0 in the SDK — a real run surfaced a 429
        # (Voyage accounts without a payment method on file are capped at
        # 3 requests/minute) from nothing more than a few `remember`/
        # `ingest_session` calls in quick succession, which is an entirely
        # realistic burst pattern in production too, not just a test
        # artifact. The SDK already implements retry-with-backoff for
        # retryable errors (429/5xx) when max_retries > 0 — this is a one-
        # line fix rather than hand-rolling retry logic here.
        self._client = AsyncClient(api_key=settings.voyage_api_key, max_retries=3)
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
