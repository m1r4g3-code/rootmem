"""The one place that decides what "the same entity name" — and "the same
entity type" — means.

Phase 1's entity resolution is deliberately minimal — exact match on these
normalized forms only, no coreference/fuzzy matching (see
docs/research/phase1-research-memo.md). Both `InMemoryGraphRepository` and
`PostgresGraphRepository` call these so names/types normalize identically
regardless of which backend is running.

`entity_type` normalization exists because a real run against the live
Anthropic API surfaced exactly the failure this predicts: extracting
"Alice works at Acme Corp" and later looking her up as entity_type="Person"
silently missed if the model had instead produced "person" (or any other
casing/whitespace variant) — the model has no reason to be consistent about
type-string casing unless told to be, and even then, treating this as a
must-match-exactly string is fragile. Normalizing at the storage boundary
(both on write and on lookup) removes the whole class of failure rather
than relying on prompt discipline alone (which is still worth doing too —
see extraction/anthropic_provider.py's system prompt — but shouldn't be the
only line of defense).
"""

from __future__ import annotations


def normalize_entity_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def normalize_entity_type(entity_type: str) -> str:
    return " ".join(entity_type.strip().lower().split())
