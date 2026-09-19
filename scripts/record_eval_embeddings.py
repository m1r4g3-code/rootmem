"""One-time script: record real voyage embeddings for the retrieval evaluation
set (ADR 0039) into tests/fixtures/eval_embeddings.json, in the same format
`FixtureReplayEmbeddingProvider` reads. Re-run only if the set changes.

Run: python scripts/record_eval_embeddings.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import voyageai

from rootmem.config import get_settings
from rootmem.evaluation.dataset import MEMORIES, QUERIES

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "eval_embeddings.json"


async def main() -> None:
    settings = get_settings()
    texts = [m.content for m in MEMORIES] + [q.text for q in QUERIES]
    client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
    result = await client.embed(
        texts, model=settings.voyage_model, output_dimension=settings.voyage_output_dimension
    )
    fixture = {
        "model": settings.voyage_model,
        "output_dimension": settings.voyage_output_dimension,
        "embeddings": dict(zip(texts, result.embeddings, strict=True)),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(fixture))
    print(f"Wrote {len(texts)} embeddings ({result.total_tokens} tokens) to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
