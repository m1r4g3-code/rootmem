"""Fixture-replay `EmbeddingProvider` fake — real recorded `voyage-4`
embeddings for a fixed sentence set, replayed offline. See ADR 0009 for why
this exists instead of a naive hash-based fake: unit tests that need
*genuine* semantic structure (e.g. proving cosine similarity actually
discriminates related from unrelated content) get it here with zero network
calls, zero API cost, and zero flakiness — a naive fake couldn't offer that
guarantee at any price.

Deliberately only serves the exact sentences recorded in
tests/fixtures/voyage_embeddings.json (see scripts/record_voyage_fixture.py,
the one-time script that produced it) — this is not a general-purpose fake,
it's a fixed, known set for tests that were written against it.
"""

from __future__ import annotations

import json
from pathlib import Path

from rootmem.embedding.protocols import EmbeddingError

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "voyage_embeddings.json"
)


class FixtureReplayEmbeddingProvider:
    def __init__(self, fixture_path: Path = _FIXTURE_PATH) -> None:
        data = json.loads(fixture_path.read_text())
        self._embeddings: dict[str, list[float]] = data["embeddings"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in self._embeddings]
        if missing:
            raise EmbeddingError(
                f"FixtureReplayEmbeddingProvider has no recorded embedding for: {missing!r} "
                "— this fake only serves the fixed sentence set in "
                "tests/fixtures/voyage_embeddings.json; add it via "
                "scripts/record_voyage_fixture.py if a new test genuinely needs it"
            )
        return [self._embeddings[t] for t in texts]
