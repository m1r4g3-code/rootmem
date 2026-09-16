"""The one place that decides what "the same entity name" means.

Phase 1's entity resolution is deliberately minimal — exact match on this
normalized form only, no coreference/fuzzy matching (see
docs/research/phase1-research-memo.md). Both `InMemoryGraphRepository` and
`PostgresGraphRepository` call this so a name normalizes identically
regardless of which backend is running — the Postgres implementation's SQL
mirrors this exact logic (lower + collapse whitespace) rather than
reimplementing it independently.
"""

from __future__ import annotations


def normalize_entity_name(name: str) -> str:
    return " ".join(name.strip().lower().split())
