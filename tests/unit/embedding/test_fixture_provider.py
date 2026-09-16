"""Proves ADR 0009's actual claim: fixture-replay embeddings have genuine
semantic structure, not just "some vector." A naive hash-based fake couldn't
make this assertion meaningfully true."""

from __future__ import annotations

import pytest

from rootmem.embedding.fakes.fixture_provider import FixtureReplayEmbeddingProvider
from rootmem.embedding.protocols import EmbeddingError
from rootmem.retrieval.ranking import cosine_similarity


@pytest.mark.asyncio
async def test_returns_recorded_embeddings_in_order() -> None:
    provider = FixtureReplayEmbeddingProvider()

    vectors = await provider.embed(["Alice works at Acme Corp", "Bob works at Acme Corp"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
    assert vectors[0] != vectors[1]


@pytest.mark.asyncio
async def test_raises_on_unrecorded_text() -> None:
    provider = FixtureReplayEmbeddingProvider()

    with pytest.raises(EmbeddingError):
        await provider.embed(["a sentence never recorded in the fixture"])


@pytest.mark.asyncio
async def test_has_genuine_semantic_structure() -> None:
    """The exit criterion's core claim, proven offline: a query with no
    lexical overlap with the relevant fact should still sit closer to it,
    in embedding space, than to an unrelated distractor."""
    provider = FixtureReplayEmbeddingProvider()

    query, related_fact, distractor = await provider.embed(
        [
            "who is employed there currently",
            "Alice joined Globex as an engineer",
            "a completely different sentence involving rainfall totals",
        ]
    )

    sim_to_related = cosine_similarity(query, related_fact)
    sim_to_distractor = cosine_similarity(query, distractor)

    assert sim_to_related > sim_to_distractor
