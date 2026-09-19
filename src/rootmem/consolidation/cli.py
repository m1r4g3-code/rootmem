"""CLI entrypoint for consolidation — no new worker infrastructure (ADR
0012): an operator or a scheduled job (cron, Task Scheduler, a CI cron job)
runs this directly instead of ROOTMEM managing its own scheduler.

Checks the trigger condition unless `--force` bypasses it, prints the
resulting `ConsolidationRun` (or a clean no-op message) as JSON to stdout.

Usage:
    uv run python -m rootmem.consolidation.cli --namespace default
    uv run python -m rootmem.consolidation.cli --namespace default --force
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rootmem.config import get_settings
from rootmem.consolidation.anthropic_distillation_provider import AnthropicDistillationProvider
from rootmem.consolidation.anthropic_procedural_distillation_provider import (
    AnthropicProceduralDistillationProvider,
)
from rootmem.consolidation.distill import maybe_run_consolidation
from rootmem.embedding.voyage import VoyageEmbeddingProvider
from rootmem.extraction.contradiction import BayesianSettings
from rootmem.logging import configure_logging, get_logger
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.consolidation_repository import PostgresConsolidationRepository
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.postgres.repository import PostgresMemoryRepository


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="default")
    parser.add_argument(
        "--force", action="store_true", help="bypass the trigger check and run unconditionally"
    )
    return parser.parse_args(argv)


async def _run(argv: list[str]) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    pool = await create_pool(settings)
    try:
        memory_repository = PostgresMemoryRepository(
            pool, settings.hybrid_search_weight_text, settings.hybrid_search_weight_vector
        )
        graph_repository = PostgresGraphRepository(pool, BayesianSettings.from_settings(settings))
        consolidation_repository = PostgresConsolidationRepository(pool)
        distillation_provider = AnthropicDistillationProvider(settings)
        embedding_provider = VoyageEmbeddingProvider(settings)
        procedural_memory_repository = PostgresProceduralMemoryRepository(pool)
        procedural_distillation_provider = AnthropicProceduralDistillationProvider(settings)

        result = await maybe_run_consolidation(
            memory_repository,
            graph_repository,
            consolidation_repository,
            distillation_provider,
            embedding_provider,
            procedural_memory_repository,
            procedural_distillation_provider,
            args.namespace,
            settings,
            force=args.force,
        )
        if result is None:
            print('{"ran": false, "reason": "trigger condition not met"}')
            logger.info("operation=consolidation_cli outcome=no_op namespace=%s", args.namespace)
            return 0
        print(result.model_dump_json(indent=2))
        logger.info("operation=consolidation_cli outcome=success run_id=%s", result.id)
        return 0
    finally:
        await pool.close()


def main() -> None:
    sys.exit(asyncio.run(_run(sys.argv[1:])))


if __name__ == "__main__":
    main()
