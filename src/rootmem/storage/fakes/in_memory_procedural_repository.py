"""Dict-backed `ProceduralMemoryRepository` fake — zero I/O, used by all unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from rootmem.retrieval.ranking import cosine_similarity, hybrid_score
from rootmem.storage.procedural_protocols import (
    NewProceduralMemory,
    ProceduralMemoryRecord,
    ProceduralSearchResult,
)


class InMemoryProceduralMemoryRepository:
    def __init__(self) -> None:
        self._records: dict[str, ProceduralMemoryRecord] = {}
        self._provenance: set[tuple[str, str]] = set()

    async def create(self, new: NewProceduralMemory) -> ProceduralMemoryRecord:
        now = datetime.now(UTC)
        new_id = str(uuid.uuid4())
        previous = await self.get_by_name(new.namespace, new.name)

        record = ProceduralMemoryRecord(
            id=new_id,
            namespace=new.namespace,
            kind=new.kind,
            name=new.name,
            description=new.description,
            body_markdown=new.body_markdown,
            content_embedding=new.content_embedding,
            supersedes=previous.id if previous is not None else None,
            created_at=now,
            updated_at=now,
        )
        self._records[new_id] = record

        if previous is not None:
            updated_previous = previous.model_copy(
                update={"superseded_by": new_id, "updated_at": now}
            )
            self._records[previous.id] = updated_previous

        return record

    async def get_by_name(self, namespace: str, name: str) -> ProceduralMemoryRecord | None:
        for record in self._records.values():
            if record.namespace == namespace and record.name == name and record.is_active:
                return record
        return None

    async def record_outcome(
        self, namespace: str, name: str, success: bool, delta_alpha: float, delta_beta: float
    ) -> ProceduralMemoryRecord | None:
        current = await self.get_by_name(namespace, name)
        if current is None:
            return None
        updated = current.model_copy(
            update={
                "belief_alpha": current.belief_alpha + delta_alpha,
                "belief_beta": current.belief_beta + delta_beta,
                "applied_count": current.applied_count + 1,
                "success_count": current.success_count + (1 if success else 0),
            }
        )
        self._records[current.id] = updated
        return updated

    async def search_hybrid(
        self,
        namespace: str,
        query_text: str,
        query_embedding: list[float] | None,
        kind: Literal["skill", "lesson", "all"],
        limit: int,
    ) -> list[ProceduralSearchResult]:
        terms = [t for t in query_text.lower().split() if t]
        results: list[ProceduralSearchResult] = []
        for record in self._records.values():
            if record.namespace != namespace or not record.is_active:
                continue
            if kind != "all" and record.kind != kind:
                continue
            haystack = f"{record.name} {record.description} {record.body_markdown}".lower()
            text_rank = float(sum(haystack.count(term) for term in terms))
            cosine_sim = (
                cosine_similarity(query_embedding, record.content_embedding)
                if query_embedding is not None and record.content_embedding is not None
                else 0.0
            )
            if text_rank == 0.0 and cosine_sim == 0.0:
                continue
            score = hybrid_score(text_rank, cosine_sim, weight_text=0.5, weight_vector=0.5)
            results.append(ProceduralSearchResult(record=record, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def link_provenance(self, procedural_memory_id: str, memory_id: str) -> None:
        self._provenance.add((procedural_memory_id, memory_id))

    async def get_provenance(self, namespace: str, procedural_memory_id: str) -> list[str]:
        return [
            memory_id
            for pm_id, memory_id in self._provenance
            if pm_id == procedural_memory_id and procedural_memory_id in self._records
        ]
