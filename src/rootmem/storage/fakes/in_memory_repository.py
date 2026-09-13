"""Dict-backed `MemoryRepository` fake — zero I/O, used by all unit tests.

Search ranking here is deliberately naive (occurrence count of query terms)
and is NOT expected to match Postgres's `ts_rank` ordering exactly; the
contract test suite asserts on which records are returned, not on identical
scores across implementations — score is an implementation detail of the
ranking algorithm, not part of the repository's behavioral contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from rootmem.storage.models import MemoryRecord, MemoryUpdate, NewMemory, SearchResult
from rootmem.storage.protocols import NotFoundError


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    async def create(self, memory: NewMemory) -> MemoryRecord:
        if memory.idempotency_key is not None:
            existing = self._find_by_idempotency_key(memory.namespace, memory.idempotency_key)
            if existing is not None:
                return existing

        now = datetime.now(UTC)
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            namespace=memory.namespace,
            key=memory.key,
            idempotency_key=memory.idempotency_key,
            content=memory.content,
            source=memory.source,
            source_session_id=memory.source_session_id,
            confidence=memory.confidence,
            metadata=memory.metadata,
            created_at=now,
            updated_at=now,
        )
        self._records[record.id] = record
        return record

    async def get_by_id(self, namespace: str, memory_id: str) -> MemoryRecord | None:
        record = self._records.get(memory_id)
        if record is None or record.namespace != namespace or record.is_deleted:
            return None
        return record

    async def get_by_key(self, namespace: str, key: str) -> MemoryRecord | None:
        for record in self._records.values():
            if record.namespace == namespace and record.key == key and not record.is_deleted:
                return record
        return None

    async def update(self, memory_id: str, changes: MemoryUpdate) -> MemoryRecord:
        record = self._records.get(memory_id)
        if record is None or record.is_deleted:
            raise NotFoundError(f"memory {memory_id!r} not found")

        updated = record.model_copy(
            update={
                "content": changes.content if changes.content is not None else record.content,
                "confidence": (
                    changes.confidence if changes.confidence is not None else record.confidence
                ),
                "metadata": (
                    changes.metadata if changes.metadata is not None else record.metadata
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        self._records[memory_id] = updated
        return updated

    async def soft_delete(self, memory_id: str, reason: str | None) -> MemoryRecord:
        record = self._records.get(memory_id)
        if record is None:
            raise NotFoundError(f"memory {memory_id!r} not found")

        if record.is_deleted:
            return record

        updated = record.model_copy(
            update={
                "deleted_at": datetime.now(UTC),
                "deleted_reason": reason,
                "updated_at": datetime.now(UTC),
            }
        )
        self._records[memory_id] = updated
        return updated

    async def search_text(
        self,
        namespace: str,
        query: str,
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        terms = [t for t in query.lower().split() if t]
        results: list[SearchResult] = []
        for record in self._records.values():
            if record.namespace != namespace or record.is_deleted:
                continue
            if source is not None and record.source != source:
                continue
            content_lower = record.content.lower()
            score = float(sum(content_lower.count(term) for term in terms))
            if score > 0:
                results.append(SearchResult(record=record, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _find_by_idempotency_key(
        self, namespace: str, idempotency_key: str
    ) -> MemoryRecord | None:
        for record in self._records.values():
            if (
                record.namespace == namespace
                and record.idempotency_key == idempotency_key
                and not record.is_deleted
            ):
                return record
        return None
