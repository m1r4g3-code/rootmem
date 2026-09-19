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
    # Added for Phase 3 (consolidation/procedural_clustering.py, session-trace
    # clustering testing): two differently-worded successful session traces
    # describing the same underlying procedure (should cluster), one failed
    # session trace on a related-looking task (should NOT cluster with the
    # successful pair -- different outcome), and one unrelated successful
    # trace (should NOT cluster with the successful pair -- different
    # procedure). Each trace is the newline-joined ordered steps of one
    # session, matching exactly how consolidation/procedural_clustering.py's
    # group_session_traces builds a trace-summary string for embedding.
    "\n".join(
        [
            "The test suite fails with a KeyError in the payment module.",
            "The root cause is a missing default value in the config loader.",
            "The fix is to add a default value in the config loader, and the tests pass.",
        ]
    ),
    "\n".join(
        [
            "A test is failing due to a KeyError inside payment processing.",
            "Root cause: the config loader has no default value set.",
            "Fix applied: added a default value to the config loader; tests now pass.",
        ]
    ),
    "\n".join(
        [
            "The test suite fails with a TypeError in the billing module.",
            "Attempted fix: changed the input type in the billing handler.",
            "The fix did not work; the TypeError persisted because the root cause "
            "was actually a serialization bug in the API layer, not the input type.",
        ]
    ),
    "\n".join(
        [
            "The deployment pipeline was hanging on the docker build step.",
            "The root cause was a stale layer cache pointing at a deleted base image.",
            "Clearing the build cache and rebuilding fixed the pipeline; "
            "it now completes normally.",
        ]
    ),
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
