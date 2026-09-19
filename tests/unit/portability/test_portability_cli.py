from __future__ import annotations

from pathlib import Path

import pytest

from rootmem.audit.chain import verify_chain
from rootmem.portability.cli import build_parser, run
from rootmem.storage.fakes.in_memory_audit_repository import InMemoryAuditLogRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_portability_repository import InMemoryPortabilityRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.graph_models import NewEntity
from rootmem.storage.models import NewMemory


async def _rig() -> tuple[InMemoryPortabilityRepository, InMemoryAuditLogRepository]:
    memories = InMemoryMemoryRepository()
    graph = InMemoryGraphRepository()
    skills = InMemoryProceduralMemoryRepository()
    await memories.create(NewMemory(namespace="src", content="alpha fact", source="t"))
    await graph.upsert_entity(NewEntity(namespace="src", entity_type="Person", name="Alice"))
    return InMemoryPortabilityRepository(memories, graph, skills), InMemoryAuditLogRepository()


async def test_export_then_import_writes_an_audit_entry_with_the_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    portability, audit = await _rig()
    bundle_path = tmp_path / "bundle.jsonl"

    assert (
        await run(
            build_parser().parse_args(["export", "--namespace", "src", "--out", str(bundle_path)]),
            portability,
            audit,
        )
        == 0
    )
    digest = capsys.readouterr().out.split("content sha256: ")[1].strip()

    assert (
        await run(
            build_parser().parse_args(
                ["import", "--namespace", "dst", "--in", str(bundle_path), "--actor", "ops"]
            ),
            portability,
            audit,
        )
        == 0
    )

    (entry,) = await audit.list_entries("dst")
    assert entry.action == "import" and entry.actor == "ops"
    assert entry.payload["bundle_sha256"] == digest
    assert entry.payload["source_namespace"] == "src"
    assert entry.payload["counts"]["memory"] == 1
    assert verify_chain([entry]).valid is True
    assert await audit.list_entries("src") == []  # export is a read, not audited


async def test_import_refuses_a_non_empty_namespace_and_writes_no_audit_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    portability, audit = await _rig()
    bundle_path = tmp_path / "bundle.jsonl"
    await run(
        build_parser().parse_args(["export", "--namespace", "src", "--out", str(bundle_path)]),
        portability,
        audit,
    )

    code = await run(
        build_parser().parse_args(["import", "--namespace", "src", "--in", str(bundle_path)]),
        portability,
        audit,
    )

    assert code == 1
    assert "not empty" in capsys.readouterr().err
    assert await audit.list_entries("src") == []


async def test_import_refuses_a_tampered_or_missing_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    portability, audit = await _rig()
    bundle_path = tmp_path / "bundle.jsonl"
    await run(
        build_parser().parse_args(["export", "--namespace", "src", "--out", str(bundle_path)]),
        portability,
        audit,
    )
    bundle_path.write_text(bundle_path.read_text().replace("alpha fact", "evil fact"))

    for path in (bundle_path, tmp_path / "missing.jsonl"):
        code = await run(
            build_parser().parse_args(["import", "--namespace", "dst", "--in", str(path)]),
            portability,
            audit,
        )
        assert code == 1
    assert "cannot use bundle" in capsys.readouterr().err
    assert await audit.list_entries("dst") == []
