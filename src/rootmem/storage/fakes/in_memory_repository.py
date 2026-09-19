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

from rootmem.retrieval.ranking import cosine_similarity, hybrid_score
from rootmem.storage.models import MemoryRecord, MemoryUpdate, NewMemory, SearchResult
from rootmem.storage.protocols import NotFoundError


class InMemoryMemoryRepository:
    def __init__(self, weight_text: float = 0.5, weight_vector: float = 0.5) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._weight_text = weight_text
        self._weight_vector = weight_vector

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
            content_embedding=memory.content_embedding,
            source=memory.source,
            source_session_id=memory.source_session_id,
            confidence=memory.confidence,
            importance_flag=memory.importance_flag,
            session_outcome=memory.session_outcome,
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
                "metadata": (changes.metadata if changes.metadata is not None else record.metadata),
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

    async def search_semantic(
        self,
        namespace: str,
        query_embedding: list[float],
        limit: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        for record in self._records.values():
            if record.namespace != namespace or record.is_deleted:
                continue
            if source is not None and record.source != source:
                continue
            if record.content_embedding is None:
                continue
            score = cosine_similarity(query_embedding, record.content_embedding)
            results.append(SearchResult(record=record, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def search_hybrid(
        self,
        namespace: str,
        query: str,
        query_embedding: list[float],
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
            text_rank = float(sum(content_lower.count(term) for term in terms))
            cosine_sim = (
                cosine_similarity(query_embedding, record.content_embedding)
                if record.content_embedding is not None
                else 0.0
            )
            if text_rank == 0.0 and cosine_sim == 0.0:
                continue
            score = hybrid_score(text_rank, cosine_sim, self._weight_text, self._weight_vector)
            results.append(SearchResult(record=record, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def count_unconsolidated(self, namespace: str) -> int:
        return sum(
            1
            for record in self._records.values()
            if record.namespace == namespace
            and not record.is_deleted
            and record.consolidated_at is None
        )

    async def list_unconsolidated(self, namespace: str, limit: int) -> list[MemoryRecord]:
        candidates = [
            record
            for record in self._records.values()
            if record.namespace == namespace
            and not record.is_deleted
            and record.consolidated_at is None
        ]
        candidates.sort(key=lambda r: r.created_at)
        return candidates[:limit]

    async def mark_consolidated(self, memory_ids: list[str], consolidated_at: datetime) -> None:
        for memory_id in memory_ids:
            record = self._records.get(memory_id)
            if record is not None:
                self._records[memory_id] = record.model_copy(
                    update={"consolidated_at": consolidated_at}
                )

    async def namespace_of(self, memory_id: str) -> str | None:
        record = self._records.get(memory_id)
        return record.namespace if record is not None else None

    async def record_access(self, memory_ids: list[str], accessed_at: datetime) -> None:
        for memory_id in memory_ids:
            record = self._records.get(memory_id)
            if record is not None and not record.is_deleted:
                self._records[memory_id] = record.model_copy(
                    update={
                        "last_accessed_at": accessed_at,
                        "access_count": record.access_count + 1,
                    }
                )

    async def update_salience(self, memory_id: str, salience_score: float) -> None:
        record = self._records.get(memory_id)
        if record is not None:
            self._records[memory_id] = record.model_copy(update={"salience_score": salience_score})

    async def find_similar_pairs(
        self, namespace: str, memory_ids: list[str], threshold: float
    ) -> list[tuple[str, str, float]]:
        candidates = [
            self._records[mid]
            for mid in memory_ids
            if mid in self._records
            and self._records[mid].namespace == namespace
            and self._records[mid].content_embedding is not None
        ]
        pairs: list[tuple[str, str, float]] = []
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 :]:
                assert a.content_embedding is not None
                assert b.content_embedding is not None
                similarity = cosine_similarity(a.content_embedding, b.content_embedding)
                if similarity >= threshold:
                    pairs.append((a.id, b.id, similarity))
        return pairs

    def _find_by_idempotency_key(self, namespace: str, idempotency_key: str) -> MemoryRecord | None:
        for record in self._records.values():
            if (
                record.namespace == namespace
                and record.idempotency_key == idempotency_key
                and not record.is_deleted
            ):
                return record
        return None
