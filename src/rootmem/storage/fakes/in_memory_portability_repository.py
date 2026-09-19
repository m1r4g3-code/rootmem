"""In-memory `PortabilityRepository` for unit tests. It composes the three
in-memory repositories it exports from and imports into (a test double may
read their internals)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from rootmem.portability.bundle import Bundle, BundleRecord, build_bundle
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.graph_models import EntityRecord, RelationRecord
from rootmem.storage.graph_normalize import normalize_entity_name, normalize_entity_type
from rootmem.storage.models import MemoryRecord
from rootmem.storage.portability_protocols import NamespaceNotEmptyError
from rootmem.storage.procedural_protocols import ProceduralMemoryRecord


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class InMemoryPortabilityRepository:
    def __init__(
        self,
        memories: InMemoryMemoryRepository,
        graph: InMemoryGraphRepository,
        skills: InMemoryProceduralMemoryRepository,
    ) -> None:
        self._memories = memories
        self._graph = graph
        self._skills = skills

    async def export_namespace(self, namespace: str) -> Bundle:
        records: list[BundleRecord] = []
        memories = {
            m.id: m
            for m in self._memories._records.values()
            if m.namespace == namespace and not m.is_deleted
        }
        for m in memories.values():
            records.append(
                BundleRecord(
                    kind="memory",
                    data={
                        "id": m.id,
                        "key": m.key,
                        "content": m.content,
                        "source": m.source,
                        "source_session_id": m.source_session_id,
                        "confidence": m.confidence,
                        "importance_flag": m.importance_flag,
                        "salience_score": m.salience_score,
                        "consolidated_at": _iso(m.consolidated_at),
                        "session_outcome": m.session_outcome,
                        "last_accessed_at": _iso(m.last_accessed_at),
                        "access_count": m.access_count,
                        "metadata": m.metadata,
                        "created_at": _iso(m.created_at),
                    },
                )
            )
        entities = {e.id: e for e in self._graph._entities.values() if e.namespace == namespace}
        for e in entities.values():
            records.append(
                BundleRecord(
                    kind="entity",
                    data={
                        "id": e.id,
                        "entity_type": e.entity_type,
                        "name": e.name,
                        "attributes": e.attributes,
                        "created_at": _iso(e.created_at),
                    },
                )
            )
        relations = {r.id: r for r in self._graph._relations.values() if r.namespace == namespace}
        for r in relations.values():
            records.append(
                BundleRecord(
                    kind="relation",
                    data={
                        "id": r.id,
                        "subject_entity_id": r.subject_entity_id,
                        "predicate": r.predicate,
                        "object_entity_id": r.object_entity_id,
                        "object_literal": r.object_literal,
                        "confidence": r.confidence,
                        "belief_alpha": r.belief_alpha,
                        "belief_beta": r.belief_beta,
                        "valid_from": _iso(r.valid_from),
                        "valid_to": _iso(r.valid_to),
                        "recorded_at": _iso(r.recorded_at),
                        "supersedes": r.supersedes,
                        "superseded_by": r.superseded_by,
                        "derivation": r.derivation,
                        "source_memory_id": r.source_memory_id,
                        "metadata": r.metadata,
                    },
                )
            )
        for memory_id, entity_id in self._graph._memory_entities:
            if memory_id in memories and entity_id in entities:
                records.append(
                    BundleRecord(
                        kind="memory_entity",
                        data={"memory_id": memory_id, "entity_id": entity_id},
                    )
                )
        for relation_id, memory_id in self._graph._relation_provenance:
            if relation_id in relations and memory_id in memories:
                records.append(
                    BundleRecord(
                        kind="relation_provenance",
                        data={"relation_id": relation_id, "memory_id": memory_id},
                    )
                )
        skills = {
            s.id: s
            for s in self._skills._records.values()
            if s.namespace == namespace and s.is_active
        }
        for s in skills.values():
            records.append(
                BundleRecord(
                    kind="skill",
                    data={
                        "id": s.id,
                        "kind": s.kind,
                        "name": s.name,
                        "description": s.description,
                        "body_markdown": s.body_markdown,
                        "derivation": s.derivation,
                        "belief_alpha": s.belief_alpha,
                        "belief_beta": s.belief_beta,
                        "applied_count": s.applied_count,
                        "success_count": s.success_count,
                        "created_at": _iso(s.created_at),
                    },
                )
            )
        for skill_id, memory_id in self._skills._provenance:
            if skill_id in skills and memory_id in memories:
                records.append(
                    BundleRecord(
                        kind="skill_provenance",
                        data={"procedural_memory_id": skill_id, "memory_id": memory_id},
                    )
                )
        return build_bundle(namespace, records, datetime.now(UTC))

    def _has_data(self, namespace: str) -> bool:
        return (
            any(m.namespace == namespace for m in self._memories._records.values())
            or any(e.namespace == namespace for e in self._graph._entities.values())
            or any(s.namespace == namespace for s in self._skills._records.values())
        )

    async def import_bundle(self, target_namespace: str, bundle: Bundle) -> dict[str, int]:
        if self._has_data(target_namespace):
            raise NamespaceNotEmptyError(target_namespace)
        now = datetime.now(UTC)
        counts = {kind: 0 for kind in bundle.manifest.counts}
        memory_ids: dict[str, str] = {}
        entity_ids: dict[str, str] = {}
        relation_ids: dict[str, str] = {}
        skill_ids: dict[str, str] = {}

        for d in bundle.of_kind("memory"):
            new_id = str(uuid.uuid4())
            memory_ids[d["id"]] = new_id
            created = _dt(d["created_at"]) or now
            self._memories._records[new_id] = MemoryRecord(
                id=new_id,
                namespace=target_namespace,
                key=d["key"],
                content=d["content"],
                source=d["source"],
                source_session_id=d["source_session_id"],
                confidence=d["confidence"],
                importance_flag=d["importance_flag"],
                salience_score=d["salience_score"],
                consolidated_at=_dt(d["consolidated_at"]),
                session_outcome=d["session_outcome"],
                last_accessed_at=_dt(d["last_accessed_at"]),
                access_count=d["access_count"],
                metadata=d["metadata"],
                created_at=created,
                updated_at=created,
            )
            counts["memory"] += 1
        for d in bundle.of_kind("entity"):
            new_id = str(uuid.uuid4())
            entity_ids[d["id"]] = new_id
            created = _dt(d["created_at"]) or now
            self._graph._entities[new_id] = EntityRecord(
                id=new_id,
                namespace=target_namespace,
                entity_type=normalize_entity_type(d["entity_type"]),
                name=d["name"],
                canonical_key=normalize_entity_name(d["name"]),
                attributes=d["attributes"],
                created_at=created,
                updated_at=created,
            )
            counts["entity"] += 1
        for d in bundle.of_kind("relation"):
            relation_ids[d["id"]] = str(uuid.uuid4())
        for d in bundle.of_kind("relation"):
            new_id = relation_ids[d["id"]]
            self._graph._relations[new_id] = RelationRecord(
                id=new_id,
                namespace=target_namespace,
                subject_entity_id=entity_ids[d["subject_entity_id"]],
                predicate=d["predicate"],
                object_entity_id=entity_ids.get(d["object_entity_id"] or ""),
                object_literal=d["object_literal"],
                confidence=d["confidence"],
                belief_alpha=d["belief_alpha"],
                belief_beta=d["belief_beta"],
                valid_from=_dt(d["valid_from"]) or now,
                valid_to=_dt(d["valid_to"]),
                recorded_at=_dt(d["recorded_at"]) or now,
                supersedes=relation_ids.get(d["supersedes"] or ""),
                superseded_by=relation_ids.get(d["superseded_by"] or ""),
                derivation=d["derivation"],
                source_memory_id=memory_ids.get(d["source_memory_id"] or ""),
                metadata=d["metadata"],
            )
            counts["relation"] += 1
        for d in bundle.of_kind("memory_entity"):
            self._graph._memory_entities.add(
                (memory_ids[d["memory_id"]], entity_ids[d["entity_id"]])
            )
            counts["memory_entity"] += 1
        for d in bundle.of_kind("relation_provenance"):
            self._graph._relation_provenance.add(
                (relation_ids[d["relation_id"]], memory_ids[d["memory_id"]])
            )
            counts["relation_provenance"] += 1
        for d in bundle.of_kind("skill"):
            new_id = str(uuid.uuid4())
            skill_ids[d["id"]] = new_id
            created = _dt(d["created_at"]) or now
            self._skills._records[new_id] = ProceduralMemoryRecord(
                id=new_id,
                namespace=target_namespace,
                kind=d["kind"],
                name=d["name"],
                description=d["description"],
                body_markdown=d["body_markdown"],
                derivation=d["derivation"],
                belief_alpha=d["belief_alpha"],
                belief_beta=d["belief_beta"],
                applied_count=d["applied_count"],
                success_count=d["success_count"],
                created_at=created,
                updated_at=created,
            )
            counts["skill"] += 1
        for d in bundle.of_kind("skill_provenance"):
            self._skills._provenance.add(
                (skill_ids[d["procedural_memory_id"]], memory_ids[d["memory_id"]])
            )
            counts["skill_provenance"] += 1
        return counts
