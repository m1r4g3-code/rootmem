"""Real calls to the live Voyage API — costs money per run (NFR6), so this
is marked `integration_external`, not the default `integration` marker
(kept out of the free Docker-only CI job, see .github/workflows/ci.yml).

Requires VOYAGE_API_KEY set (see .env).
"""

from __future__ import annotations

import pytest

from rootmem.config import get_settings
from rootmem.embedding.voyage import VoyageEmbeddingProvider
from rootmem.retrieval.ranking import cosine_similarity


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_embed_returns_configured_dimension() -> None:
    settings = get_settings()
    provider = VoyageEmbeddingProvider(settings)

    vectors = await provider.embed(["a short test sentence"])

    assert len(vectors) == 1
    assert len(vectors[0]) == settings.voyage_output_dimension


@pytest.mark.integration_external
@pytest.mark.asyncio
async def test_embed_has_real_semantic_structure() -> None:
    settings = get_settings()
    provider = VoyageEmbeddingProvider(settings)

    query, related, distractor = await provider.embed(
        [
            "who is employed there currently",
            "Alice joined Globex as an engineer",
            "a completely different sentence involving rainfall totals",
        ]
    )

    assert cosine_similarity(query, related) > cosine_similarity(query, distractor)
