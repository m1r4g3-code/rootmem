"""One-time (re-run only if the fixed sentence set below changes) script
that records real voyage-4 embeddings into tests/fixtures/voyage_embeddings.json
for FixtureReplayEmbeddingProvider (ADR 0009). Throwaway — not part of the
shipped package, not covered by mypy/ruff's src/tests scope.

Run: uv run python scripts/record_voyage_fixture.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import voyageai

from rootmem.config import get_settings

SENTENCES = [
    "Alice works at Acme Corp",
    "Alice joined Globex as an engineer",
    "where is Alice employed now",
    "who is employed there currently",
    "a completely different sentence involving rainfall totals",
    "the weather forecast predicts heavy rain this weekend",
    "Bob works at Acme Corp",
    "the sky is blue and the grass is green",
    # Added for Phase 2 (consolidation/clustering, corroboration testing):
    # near-duplicate restatements of the same fact, for similarity-threshold
    # union-find clustering (ADR 0015) and Bayesian corroboration (ADR 0013)
    # tests to exercise genuine near-duplicate structure, not synthetic
    # hash-based stand-ins.
    "Alice is employed at Acme Corp",
    "Alice's employer is Acme Corp",
    "The engineering team relocated to a new office at 500 Market Street.",
]

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "voyage_embeddings.json"
)


async def main() -> None:
    settings = get_settings()
    client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    result = await client.embed(
        SENTENCES, model=settings.voyage_model, output_dimension=settings.voyage_output_dimension
    )

    fixture = {
        "model": settings.voyage_model,
        "output_dimension": settings.voyage_output_dimension,
        "embeddings": dict(zip(SENTENCES, result.embeddings, strict=True)),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"Wrote {len(SENTENCES)} embeddings ({result.total_tokens} tokens) to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
