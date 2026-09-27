"""Tiny, shared environment-variable parsing for the hook entrypoints in this
package. Malformed configuration must never crash a hook (ADR 0044) — a bad
`ROOTMEM_AUTO_RECALL_LIMIT` falls back to its default rather than raising.
"""

from __future__ import annotations


def env_int(environ: dict[str, str], name: str, default: int) -> int:
    try:
        return int(environ[name])
    except (KeyError, ValueError):
        return default


def env_float(environ: dict[str, str], name: str, default: float) -> float:
    try:
        return float(environ[name])
    except (KeyError, ValueError):
        return default
