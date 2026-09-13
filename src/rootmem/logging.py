"""Structured logging setup.

Configures a single named logger ("rootmem") with a consistent format.
Per-operation latency/outcome instrumentation lives in
`rootmem.observability.metrics` (a separate, cross-cutting layer per the
charter's layer-isolation mandate), not here.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "rootmem"


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
