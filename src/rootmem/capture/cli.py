"""CLI entrypoint for capture — session-lifecycle hooks and batch import
(ADR 0010: a CLI + MCP tool, deliberately not an HTTP webhook listener).

Reads a transcript from stdin (or a file, via `--file`), ingests it, and
prints the resulting `IngestResult` as JSON to stdout — the shape a
client-side hook (e.g. Claude Code's `hooks.json` `SessionEnd` hook, see
docs/capture-hook-example.md) can shell out to.

Usage:
    uv run python -m rootmem.capture.cli --source claude-code < transcript.txt
    uv run python -m rootmem.capture.cli --file transcript.txt --source claude-code \
        --session-id abc123
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rootmem.capture.ingest import ingest_transcript
from rootmem.config import get_settings
from rootmem.embedding.voyage import VoyageEmbeddingProvider
from rootmem.extraction.anthropic_provider import AnthropicExtractionProvider
from rootmem.logging import configure_logging, get_logger
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.repository import PostgresMemoryRepository


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--source", required=True)
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="read the transcript from this file instead of stdin",
    )
    return parser.parse_args(argv)


async def _run(argv: list[str]) -> int:
    args = _parse_args(argv)
    content = args.file.read_text() if args.file is not None else sys.stdin.read()
    if not content.strip():
        print("error: transcript is empty", file=sys.stderr)
        return 1

    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    pool = await create_pool(settings)
    try:
        memory_repository = PostgresMemoryRepository(
            pool, settings.hybrid_search_weight_text, settings.hybrid_search_weight_vector
        )
        graph_repository = PostgresGraphRepository(pool, settings.contradiction_confidence_floor)
        embedding_provider = VoyageEmbeddingProvider(settings)
        extraction_provider = AnthropicExtractionProvider(settings)

        result = await ingest_transcript(
            memory_repository,
            graph_repository,
            embedding_provider,
            extraction_provider,
            namespace=args.namespace,
            content=content,
            source=args.source,
            source_session_id=args.session_id,
        )
        print(result.model_dump_json(indent=2))
        logger.info("operation=capture_cli outcome=success memory_id=%s", result.memory_id)
        return 0
    finally:
        await pool.close()


def main() -> None:
    sys.exit(asyncio.run(_run(sys.argv[1:])))


if __name__ == "__main__":
    main()
