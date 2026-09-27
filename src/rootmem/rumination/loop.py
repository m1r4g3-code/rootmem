"""The autonomous rumination loop (ADR 0049): one `asyncio` task, started in
HTTP mode only when `RUMINATION_ENABLED=true` (ADR 0051), running
`run_rumination_pass` on a wall-clock timer for as long as the server
process lives. Cancelled cleanly on server shutdown (`main_async`).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rootmem.logging import get_logger
from rootmem.rumination.run import run_rumination_pass

if TYPE_CHECKING:
    from rootmem.audit.recorder import AuditRecorder
    from rootmem.config import Settings
    from rootmem.storage.graph_protocols import GraphRepository


async def run_rumination_loop(
    graph_repository: GraphRepository, audit_recorder: AuditRecorder, settings: Settings
) -> None:
    """Runs until cancelled. A pass that raises is logged, never crashes the
    loop or the server (NFR3) -- the next scheduled pass still runs."""
    logger = get_logger()
    interval_seconds = settings.rumination_interval_minutes * 60
    while True:
        try:
            summary = await run_rumination_pass(
                graph_repository,
                audit_recorder,
                now=datetime.now(UTC),
                namespace=None,
                decay_base_stability_days=settings.decay_base_stability_days,
                supersede_margin=settings.bayesian_supersede_margin,
                min_contest_age_hours=settings.rumination_min_contest_age_hours,
            )
            if summary.pairs_resolved:
                logger.info(
                    "operation=rumination_pass outcome=success examined=%d resolved=%d",
                    summary.pairs_examined,
                    summary.pairs_resolved,
                )
        except Exception:  # noqa: BLE001 - a failed pass must never kill the loop
            logger.warning("operation=rumination_pass outcome=error", exc_info=True)
        await asyncio.sleep(interval_seconds)


__all__ = ["run_rumination_loop"]
