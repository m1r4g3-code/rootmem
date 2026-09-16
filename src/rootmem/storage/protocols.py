"""The storage port: `MemoryRepository`.

MCP tool handlers depend only on this Protocol, never on a concrete driver
(asyncpg, redis) directly — see ADR 0003. `InMemoryMemoryRepository` and
`PostgresMemoryRepository` both satisfy it and are verified against the
same contract-test suite (`tests/unit/storage/contract.py`) for behavioral
parity.
"""

from __future__ import annotations

from typing import Protocol

from rootmem.storage.models import MemoryRecord, MemoryUpdate, NewMemory, SearchResult


class NotFoundError(Exception):
    """Raised when an operation targets a record id that never existed.

    Not raised for soft-deleted records being read via recall/search
    (that's a normal "not found" result, not an error) — see
    `MemoryRepository.get_by_id` docstring.
    """


class StorageError(Exception):
    """Raised when the underlying store is unreachable or an operation fails
    for reasons outside the caller's control (e.g. connection drop)."""


class MemoryRepository(Protocol):
    async def create(self, memory: NewMemory) -> MemoryRecord:
        """Insert a new memory.

        If `memory.idempotency_key` is set and a non-deleted record already
        exists with the same (namespace, idempotency_key), returns that
        existing record instead of creating a duplicate.
        """
        ...

    async def get_by_id(self, namespace: str, memory_id: str) -> MemoryRecord | None:
        """Return the record, or None if it doesn't exist or is soft-deleted."""
        ...

    async def get_by_key(self, namespace: str, key: str) -> MemoryRecord | None:
        """Return the record, or None if it doesn't exist or is soft-deleted."""
        ...

    async def update(self, memory_id: str, changes: MemoryUpdate) -> MemoryRecord:
        """Apply a partial update to an existing, non-deleted record.

        Looked up by id alone (UUIDs are globally unique) — no namespace
        parameter, matching the `update` MCP tool's signature, which is
        deliberately narrower than `remember`/`recall`/`search` since a
        caller updating a specific record already has its id and doesn't
        need namespace scoping to find it. Cross-namespace update/forget
        access control is explicitly out of scope for Phase 0 (see the
        plan's non-goals — multi-tenant auth is Phase 6+).

        Raises NotFoundError if the id doesn't exist or is already soft-deleted.
        """
        ...

    async def soft_delete(self, memory_id: str, reason: str | None) -> MemoryRecord:
        """Soft-delete a record (sets deleted_at/deleted_reason).

        Looked up by id alone, same rationale as `update` above.

        Idempotent: calling this on an already-deleted record returns it
        unchanged rather than raising. Raises NotFoundError only if the id
        never existed at all.
        """
        ...

    async def search_text(
        self,
        namespace: str,
        query: str,
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        """Full-text search over non-deleted records, ranked by relevance."""
        ...

    async def search_semantic(
        self,
        namespace: str,
        query_embedding: list[float],
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        """Semantic search over non-deleted records with a populated
        `content_embedding`, ranked by cosine similarity to `query_embedding`
        (ADR 0007). Records with no embedding (e.g. from an embedding-provider
        failure at write time) are excluded, not scored as a non-match."""
        ...

    async def search_hybrid(
        self,
        namespace: str,
        query: str,
        query_embedding: list[float],
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        """Blend of `search_text` and `search_semantic` via
        `retrieval.ranking.hybrid_score` (docs/math-spec/phase1-math-spec.md)
        — a provisional linear combination, not the Phase 4 multi-factor
        formula. Records with no embedding fall back to a pure text-rank
        contribution (weight_vector's term is 0), so they aren't silently
        excluded just because they predate embedding population."""
        ...
