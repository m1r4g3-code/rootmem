"""The namespace portability port: `PortabilityRepository` (ADR 0037).

Exports one namespace as a `Bundle` and imports a bundle into another. It
reads and writes several aggregates at once (memories, graph, skills) and is
transactional on import, which is why it is its own Protocol rather than more
methods on the per-aggregate ones.
"""

from __future__ import annotations

from typing import Protocol

from rootmem.portability.bundle import Bundle


class NamespaceNotEmptyError(Exception):
    """Import refused: the target namespace already holds data. Importing
    into a non-empty namespace would silently duplicate or interleave
    records, so the caller must choose an empty namespace."""


class PortabilityRepository(Protocol):
    async def export_namespace(self, namespace: str) -> Bundle:
        """Export active memories, entities, relations (with belief state and
        history), links, provenance and active skills/lessons. Soft-deleted
        memories, embeddings and the audit log are not exported."""
        ...

    async def import_bundle(self, target_namespace: str, bundle: Bundle) -> dict[str, int]:
        """Import into an EMPTY namespace, atomically, with fresh ids;
        returns the per-kind counts written. Raises `NamespaceNotEmptyError`
        if the target already holds any data."""
        ...
