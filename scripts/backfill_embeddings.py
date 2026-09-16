#!/usr/bin/env python
"""Sweeps `memories` rows with `content_embedding IS NULL` (from
embedding-provider failures at write time, FR1/NFR2's graceful
degradation) and embeds them.

Usage:
    uv run python scripts/backfill_embeddings.py [--batch-size 50]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rootmem.config import get_settings
from rootmem.embedding.voyage import VoyageEmbeddingProvider
from rootmem.logging import configure_logging, get_logger
from rootmem.storage.postgres.connection import create_pool


async def _run(batch_size: int) -> int:
    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    pool = await create_pool(settings)
    try:
        embedding_provider = VoyageEmbeddingProvider(settings)
        total_updated = 0
        while True:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, content FROM memories "
                    "WHERE content_embedding IS NULL AND deleted_at IS NULL "
                    "LIMIT $1",
                    batch_size,
                )
            if not rows:
                break

            embeddings = await embedding_provider.embed([row["content"] for row in rows])
            async with pool.acquire() as conn, conn.transaction():
                for row, embedding in zip(rows, embeddings, strict=True):
                    await conn.execute(
                        "UPDATE memories SET content_embedding = $2 WHERE id = $1",
                        row["id"],
                        embedding,
                    )
            total_updated += len(rows)
            logger.info("operation=backfill_embeddings outcome=progress updated=%d", total_updated)

        print(f"Backfilled {total_updated} memory embeddings.")
        return 0
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.batch_size)))


if __name__ == "__main__":
    main()
