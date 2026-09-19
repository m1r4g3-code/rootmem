"""Shared behavioral contract for every `PortabilityRepository` implementation
(ADR 0037): export a seeded namespace, round-trip it through the JSONL bundle
into another namespace, and check what does and does not survive.

Base class, not a test file. Subclasses provide an async `env` fixture with
the portability repository AND the per-aggregate repositories it works over.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from rootmem.portability.bundle import BundleError, dump_jsonl, load_jsonl
from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.models import NewMemory
from rootmem.storage.portability_protocols import NamespaceNotEmptyError, PortabilityRepository
from rootmem.storage.procedural_protocols import NewProceduralMemory, ProceduralMemoryRepository
from rootmem.storage.protocols import MemoryRepository


@dataclass
class PortabilityEnv:
    portability: PortabilityRepository
    memories: MemoryRepository
    graph: GraphRepository
    skills: ProceduralMemoryRepository


@dataclass
class Seeded:
    namespace: str
    memory_ids: list[str]
    deleted_id: str


class PortabilityRepositoryContract:
    @pytest.fixture
    def env(self) -> PortabilityEnv:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def _ns(label: str) -> str:
        return f"port-{label}-{uuid.uuid4().hex[:8]}"

    async def _seed(self, env: PortabilityEnv) -> Seeded:
        ns = self._ns("src")
        first = await env.memories.create(
            NewMemory(
                namespace=ns,
                key="k1",
                content="Alice works at Acme Corp.",
                source="seed",
                confidence=0.9,
                importance_flag=0.5,
                metadata={"tag": "one"},
            )
        )
        second = await env.memories.create(
            NewMemory(
                namespace=ns,
                content="A test failed and the fix worked.",
                source="seed",
                session_outcome="success",
                source_session_id="sess-1",
            )
        )
        doomed = await env.memories.create(
            NewMemory(namespace=ns, content="forgotten fact", source="seed")
        )
        await env.memories.soft_delete(doomed.id, reason="seed")
        await env.memories.record_access([first.id], first.created_at)

        alice = await env.graph.upsert_entity(
            NewEntity(namespace=ns, entity_type="Person", name="Alice")
        )
        acme = await env.graph.upsert_entity(
            NewEntity(namespace=ns, entity_type="Organization", name="Acme Corp")
        )
        globex = await env.graph.upsert_entity(
            NewEntity(namespace=ns, entity_type="Organization", name="Globex")
        )
        old = await env.graph.create_relation(
            NewRelation(
                namespace=ns,
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=acme.id,
                confidence=0.8,
                source_memory_id=first.id,
                metadata={"note": "first"},
            )
        )
        await env.graph.create_relation(
            NewRelation(
                namespace=ns,
                subject_entity_id=alice.id,
                predicate="works_at",
                object_entity_id=globex.id,
                confidence=0.95,
            )
        )
        await env.graph.link_memory_entity(first.id, alice.id)
        await env.graph.link_relation_provenance(old.new.id, first.id)

        skill = await env.skills.create(
            NewProceduralMemory(
                namespace=ns,
                kind="skill",
                name="fix-the-thing",
                description="how to fix the thing",
                body_markdown="1. do it",
            )
        )
        await env.skills.record_outcome(ns, "fix-the-thing", True, 2.0, 0.0)
        await env.skills.link_provenance(skill.id, second.id)
        return Seeded(ns, [first.id, second.id], doomed.id)

    async def test_export_has_the_expected_records_and_omits_deleted_memories(
        self, env: PortabilityEnv
    ) -> None:
        seeded = await self._seed(env)

        bundle = await env.portability.export_namespace(seeded.namespace)

        counts = bundle.manifest.counts
        assert counts["memory"] == 2
        assert counts["entity"] == 3
        assert counts["relation"] == 2  # the superseded one is history, still exported
        assert counts["memory_entity"] == 1
        assert counts["relation_provenance"] == 1
        assert counts["skill"] == 1
        assert counts["skill_provenance"] == 1
        exported = {m["content"] for m in bundle.of_kind("memory")}
        assert "forgotten fact" not in exported

    async def test_bundle_round_trips_into_another_namespace(self, env: PortabilityEnv) -> None:
        seeded = await self._seed(env)
        target = self._ns("dst")
        source_bundle = await env.portability.export_namespace(seeded.namespace)

        # Through the on-disk format, so the digest check is part of the path.
        loaded = load_jsonl(dump_jsonl(source_bundle))
        written = await env.portability.import_bundle(target, loaded)
        copied = await env.portability.export_namespace(target)

        assert written == source_bundle.manifest.counts
        assert copied.manifest.counts == source_bundle.manifest.counts
        assert self._shape(copied) == self._shape(source_bundle)

    @staticmethod
    def _shape(bundle: Any) -> dict[str, Any]:
        """Content of a bundle with ids and namespaces stripped, so two
        exports of the same data under different ids compare equal."""
        memories = sorted(
            (
                m["content"],
                m["key"],
                m["source"],
                m["confidence"],
                m["importance_flag"],
                m["session_outcome"],
                m["source_session_id"],
                m["access_count"],
                str(m["metadata"]),
            )
            for m in bundle.of_kind("memory")
        )
        entity_by_id = {e["id"]: (e["entity_type"], e["name"]) for e in bundle.of_kind("entity")}
        memory_by_id = {m["id"]: m["content"] for m in bundle.of_kind("memory")}
        relation_by_id = {r["id"]: r for r in bundle.of_kind("relation")}
        relations = sorted(
            (
                entity_by_id[r["subject_entity_id"]],
                r["predicate"],
                entity_by_id.get(r["object_entity_id"] or ""),
                r["object_literal"],
                r["confidence"],
                r["belief_alpha"],
                r["belief_beta"],
                r["valid_to"] is None,
                r["derivation"],
                str(r["metadata"]),
                memory_by_id.get(r["source_memory_id"] or ""),
                # the supersede structure, expressed by object rather than id
                entity_by_id.get(
                    (relation_by_id.get(r["superseded_by"] or "") or {}).get("object_entity_id")
                    or ""
                ),
            )
            for r in bundle.of_kind("relation")
        )
        links = sorted(
            (memory_by_id[link["memory_id"]], entity_by_id[link["entity_id"]])
            for link in bundle.of_kind("memory_entity")
        )
        provenance = sorted(
            (
                entity_by_id[relation_by_id[p["relation_id"]]["subject_entity_id"]],
                memory_by_id[p["memory_id"]],
            )
            for p in bundle.of_kind("relation_provenance")
        )
        skill_by_id = {s["id"]: s["name"] for s in bundle.of_kind("skill")}
        skills = sorted(
            (
                s["kind"],
                s["name"],
                s["description"],
                s["body_markdown"],
                s["belief_alpha"],
                s["belief_beta"],
                s["applied_count"],
                s["success_count"],
            )
            for s in bundle.of_kind("skill")
        )
        skill_links = sorted(
            (skill_by_id[p["procedural_memory_id"]], memory_by_id[p["memory_id"]])
            for p in bundle.of_kind("skill_provenance")
        )
        return {
            "memories": memories,
            "relations": relations,
            "links": links,
            "provenance": provenance,
            "skills": skills,
            "skill_links": skill_links,
        }

    async def test_supersede_history_survives_the_round_trip(self, env: PortabilityEnv) -> None:
        seeded = await self._seed(env)
        target = self._ns("dst")
        await env.portability.import_bundle(
            target, await env.portability.export_namespace(seeded.namespace)
        )

        copied = await env.portability.export_namespace(target)

        relations = copied.of_kind("relation")
        superseded = [r for r in relations if r["superseded_by"] is not None]
        active = [r for r in relations if r["valid_to"] is None]
        assert len(superseded) == 1 and len(active) == 1
        assert superseded[0]["superseded_by"] == active[0]["id"]
        assert active[0]["supersedes"] == superseded[0]["id"]

    async def test_imported_records_get_fresh_ids_and_the_target_namespace(
        self, env: PortabilityEnv
    ) -> None:
        seeded = await self._seed(env)
        target = self._ns("dst")
        source_bundle = await env.portability.export_namespace(seeded.namespace)

        await env.portability.import_bundle(target, source_bundle)
        copied = await env.portability.export_namespace(target)

        source_ids = {m["id"] for m in source_bundle.of_kind("memory")}
        copied_ids = {m["id"] for m in copied.of_kind("memory")}
        assert source_ids.isdisjoint(copied_ids)
        hits = await env.memories.search_text(target, "Alice", 10)
        assert {h.record.id for h in hits} <= copied_ids and len(hits) >= 1
        # The copy is independent: forgetting the original leaves it intact.
        await env.memories.soft_delete(seeded.memory_ids[0], reason="test")
        again = await env.portability.export_namespace(target)
        assert again.manifest.counts["memory"] == 2

    async def test_import_into_a_non_empty_namespace_is_refused_and_changes_nothing(
        self, env: PortabilityEnv
    ) -> None:
        seeded = await self._seed(env)
        occupied = self._ns("occupied")
        await env.memories.create(NewMemory(namespace=occupied, content="already here", source="t"))
        bundle = await env.portability.export_namespace(seeded.namespace)

        with pytest.raises(NamespaceNotEmptyError):
            await env.portability.import_bundle(occupied, bundle)

        after = await env.portability.export_namespace(occupied)
        assert after.manifest.counts["memory"] == 1
        assert after.manifest.counts["entity"] == 0

    async def test_empty_namespace_exports_an_empty_valid_bundle(self, env: PortabilityEnv) -> None:
        bundle = await env.portability.export_namespace(self._ns("empty"))

        assert sum(bundle.manifest.counts.values()) == 0
        assert load_jsonl(dump_jsonl(bundle)).manifest == bundle.manifest

    async def test_a_tampered_bundle_never_reaches_the_repository(
        self, env: PortabilityEnv
    ) -> None:
        seeded = await self._seed(env)
        text = dump_jsonl(await env.portability.export_namespace(seeded.namespace))

        with pytest.raises(BundleError):
            load_jsonl(text.replace("Alice works at Acme Corp.", "Mallory works at Evil Inc."))
