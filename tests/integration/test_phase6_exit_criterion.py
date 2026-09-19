"""The Phase 6 exit criterion (docs/requirements/phase6-requirements.md),
proven against a real uvicorn process in HTTP mode and real Postgres.

(a) expired and pre-rotation tokens get 401; the rotated token sees the data;
(b) a `read` identity can search/recall, every write tool is denied, and the
    audit chain gains nothing from the denials;
(c) a burst is throttled for one identity while another is unaffected;
(d) /healthz answers 200 with no token and reveals only a status;
(e) the REST facade returns what MCP returns, and 401/403 as appropriate;
(f) export from A's namespace and import into B's reproduces memories, graph
    and skills, with an `import` audit entry and a valid chain;
(g) the Claude Code hook script creates a memory through REST;
(h) the retrieval evaluation runs and renders its report (numbers not gated).

(i), stdio and the earlier suites unchanged, is the rest of the suite. Marked
integration_external because `remember`/`ingest_session` call Voyage and
Anthropic. Run it ALONE, not chained with other external tests (Voyage's
free tier allows 3 requests/minute).
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest

from rootmem.client import RootmemClient, RootmemError
from rootmem.config import get_settings
from rootmem.evaluation.run import evaluate, render_markdown
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.integrations.claude_code_hook import _default_client
from rootmem.integrations.claude_code_hook import run as run_hook
from rootmem.portability.cli import build_parser
from rootmem.portability.cli import run as run_portability
from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository
from rootmem.storage.postgres.portability_repository import PostgresPortabilityRepository
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.procedural_protocols import NewProceduralMemory
from tests.integration.test_phase5_exit_criterion import (
    _call,
    _client,
    _free_port,
    _HttpServer,
    _ok,
)

pytestmark = pytest.mark.integration_external

_WRITE_TOOLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("remember", {"content": "x", "source": "t"}),
    ("consolidate", {"force": True}),
    ("ingest_session", {"transcript": "some text", "source": "t"}),
)


def _rest(url: str, token: str | None, tool: str, body: dict[str, Any]) -> httpx2.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx2.post(f"{url}/v1/tools/{tool}", json=body, headers=headers, timeout=60)


@pytest.mark.asyncio
async def test_hardening_adapters_portability_and_evaluation(tmp_path: Path) -> None:
    sfx = uuid.uuid4().hex[:8]
    ns_a, ns_b, ns_r, ns_t, ns_c = (f"p6-{x}-{sfx}" for x in ("a", "b", "r", "t", "c"))
    tok = {
        name: generate_token() for name in ("alice", "reader", "bob", "old", "rot", "busy", "calm")
    }
    pool = await create_pool(get_settings())
    server = _HttpServer(_free_port(), {"RATE_LIMIT_PER_MINUTE": "6", "RATE_LIMIT_BURST": "20"})
    base = f"http://127.0.0.1:{server.port}"
    try:
        ids = PostgresIdentityRepository(pool)
        await ids.create(f"alice-{sfx}", [ns_a], hash_token(tok["alice"]))
        await ids.create(f"reader-{sfx}", [ns_a], hash_token(tok["reader"]), scope="read")
        await ids.create(f"bob-{sfx}", [ns_b], hash_token(tok["bob"]))
        await ids.create(
            f"old-{sfx}",
            [ns_a],
            hash_token(tok["old"]),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        await ids.create(f"rot-{sfx}", [ns_r], hash_token(tok["rot"]))
        await ids.create(f"busy-{sfx}", [ns_t], hash_token(tok["busy"]))
        await ids.create(f"calm-{sfx}", [ns_c], hash_token(tok["calm"]))
        await server.start()

        # --- (d) health, unauthenticated, reveals only a status ---
        health = httpx2.get(f"{base}/healthz", timeout=30)
        assert health.status_code == 200 and health.json() == {"status": "ok"}

        # --- (a) expiry ---
        async with httpx2.AsyncClient() as raw:
            for headers in ({"Authorization": f"Bearer {tok['old']}"}, {}):
                assert (await raw.post(server.url, json={}, headers=headers)).status_code == 401
        assert (
            _rest(base, tok["old"], "search", {"query": "q", "namespace": ns_a}).status_code == 401
        )

        # --- seed A over MCP (three embeddings), then pace for Voyage's 3 RPM ---
        async with _client(server.url, tok["alice"]) as alice:
            first = _ok(
                await _call(
                    alice,
                    "remember",
                    content="The deploy window is Thursday 3pm.",
                    source="p6",
                    namespace=ns_a,
                )
            )
            second = _ok(
                await _call(
                    alice,
                    "remember",
                    content="Backups run at 02:00 UTC nightly.",
                    source="p6",
                    namespace=ns_a,
                )
            )
        async with _client(server.url, tok["rot"]) as rot_client:
            rotated_memory = _ok(
                await _call(
                    rot_client,
                    "remember",
                    content="rotation canary fact",
                    source="p6",
                    namespace=ns_r,
                )
            )["id"]
        await asyncio.sleep(35)

        # --- (a) rotation: the old token dies at once, the new one sees the data ---
        new_rot_token = generate_token()
        await ids.rotate(f"rot-{sfx}", hash_token(new_rot_token))
        async with httpx2.AsyncClient() as raw:
            dead = await raw.post(
                server.url, json={}, headers={"Authorization": f"Bearer {tok['rot']}"}
            )
        assert dead.status_code == 401
        async with _client(server.url, new_rot_token) as rot_client:
            recalled = _ok(await _call(rot_client, "recall", id=rotated_memory, namespace=ns_r))
        assert recalled["record"]["content"] == "rotation canary fact"

        # --- graph and skill seeding for the export (direct, like Phase 4's skills) ---
        graph = PostgresGraphRepository(pool)
        person = await graph.upsert_entity(
            NewEntity(namespace=ns_a, entity_type="Person", name="Alice")
        )
        org = await graph.upsert_entity(
            NewEntity(namespace=ns_a, entity_type="Organization", name="Acme")
        )
        relation = await graph.create_relation(
            NewRelation(
                namespace=ns_a,
                subject_entity_id=person.id,
                predicate="works_at",
                object_entity_id=org.id,
                confidence=0.9,
                source_memory_id=first["id"],
            )
        )
        await graph.link_memory_entity(first["id"], person.id)
        await graph.link_relation_provenance(relation.new.id, first["id"])
        skills = PostgresProceduralMemoryRepository(pool)
        skill = await skills.create(
            NewProceduralMemory(
                namespace=ns_a,
                kind="skill",
                name="ship-on-thursday",
                description="how to ship",
                body_markdown="1. wait for Thursday",
            )
        )
        await skills.link_provenance(skill.id, second["id"])

        # --- (b) read scope: reads work, every write is denied, nothing is audited ---
        audit = PostgresAuditLogRepository(pool)
        entries_before = len(await audit.list_entries(ns_a))
        async with _client(server.url, tok["reader"]) as reader:
            found = _ok(
                await _call(reader, "search", query="deploy window", namespace=ns_a, mode="text")
            )
            assert first["id"] in [item["id"] for item in found["results"]]
            _ok(await _call(reader, "recall", id=second["id"], namespace=ns_a))
            for tool, args in _WRITE_TOOLS:
                assert (await _call(reader, tool, namespace=ns_a, **args)).is_error is True, tool
            for tool, args in (
                ("update", {"id": first["id"], "content": "x"}),
                ("forget", {"id": first["id"]}),
            ):
                assert (await _call(reader, tool, **args)).is_error is True, tool
        assert (
            _rest(
                base, tok["reader"], "remember", {"content": "x", "source": "t", "namespace": ns_a}
            ).status_code
            == 403
        )
        assert len(await audit.list_entries(ns_a)) == entries_before

        # --- (e) REST parity with MCP, and 401/403 ---
        via_rest = _rest(
            base,
            tok["alice"],
            "search",
            {"query": "deploy window", "namespace": ns_a, "mode": "text"},
        )
        assert via_rest.status_code == 200
        async with _client(server.url, tok["alice"]) as alice:
            via_mcp = _ok(
                await _call(alice, "search", query="deploy window", namespace=ns_a, mode="text")
            )
        assert [r["id"] for r in via_rest.json()["result"]["results"]] == [
            r["id"] for r in via_mcp["results"]
        ]
        assert _rest(base, None, "search", {"query": "q", "namespace": ns_a}).status_code == 401
        assert (
            _rest(base, tok["bob"], "search", {"query": "q", "namespace": ns_a}).status_code == 403
        )
        client = RootmemClient(base, tok["alice"])
        assert (await asyncio.to_thread(client.search, "deploy window", namespace=ns_a, limit=3))[
            "results"
        ]
        with pytest.raises(RootmemError) as denied:
            await asyncio.to_thread(RootmemClient(base, tok["bob"]).search, "q", namespace=ns_a)
        assert denied.value.status_code == 403

        # --- (c) rate limit: the busy identity is throttled, the calm one is not ---
        statuses = [
            _rest(
                base, tok["busy"], "search", {"query": "q", "namespace": ns_t, "mode": "text"}
            ).status_code
            for _ in range(40)
        ]
        assert 200 in statuses and 429 in statuses
        assert (
            _rest(
                base, tok["calm"], "search", {"query": "q", "namespace": ns_c, "mode": "text"}
            ).status_code
            == 200
        )

        # --- (f) export A, import into B, verify through B's own identity ---
        bundle_file = tmp_path / "bundle.jsonl"
        portability = PostgresPortabilityRepository(pool)
        export_args = build_parser().parse_args(
            ["export", "--namespace", ns_a, "--out", str(bundle_file)]
        )
        assert await run_portability(export_args, portability, audit) == 0
        import_args = build_parser().parse_args(
            ["import", "--namespace", ns_b, "--in", str(bundle_file), "--actor", "phase6-test"]
        )
        assert await run_portability(import_args, portability, audit) == 0
        async with _client(server.url, tok["bob"]) as bob:
            copied = _ok(
                await _call(bob, "search", query="deploy window", namespace=ns_b, mode="text")
            )
            assert any("Thursday" in item["content"] for item in copied["results"])
            skill_copy = _ok(await _call(bob, "get_skill", name="ship-on-thursday", namespace=ns_b))
            assert skill_copy["found"] is True
            related = _ok(
                await _call(
                    bob, "related", entity_name="Alice", entity_type="Person", namespace=ns_b
                )
            )
            assert related["relations"]
            verified = _ok(await _call(bob, "verify_audit", namespace=ns_b))
            assert verified["valid"] is True
        import_entries = [e for e in await audit.list_entries(ns_b) if e.action == "import"]
        assert len(import_entries) == 1 and import_entries[0].actor == "phase6-test"

        # --- (g) the Claude Code hook creates a memory through REST ---
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": (
                            "Please remember that the canary release for Zephyr "
                            "goes out on Wednesday."
                        ),
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "Noted: the Zephyr canary release is on Wednesday.",
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        hook_stderr = io.StringIO()
        hook_code = await asyncio.to_thread(
            run_hook,
            io.StringIO(json.dumps({"transcript_path": str(transcript), "session_id": f"s-{sfx}"})),
            {
                "ROOTMEM_URL": base,
                "ROOTMEM_TOKEN": tok["alice"],
                "ROOTMEM_NAMESPACE": ns_a,
                "ROOTMEM_SOURCE": "claude-code-hook",
            },
            _default_client,
            hook_stderr,
        )
        assert hook_code == 0, hook_stderr.getvalue()
        async with _client(server.url, tok["alice"]) as alice:
            hooked = _ok(
                await _call(alice, "search", query="Zephyr canary", namespace=ns_a, mode="text")
            )
            assert any(item["source"] == "claude-code-hook" for item in hooked["results"])
            assert _ok(await _call(alice, "verify_audit", namespace=ns_a))["valid"] is True

        # --- (h) the retrieval evaluation runs and renders its report ---
        report_text = render_markdown(await evaluate())
        (tmp_path / "eval.md").write_text(report_text, encoding="utf-8")
        assert "## Overall" in report_text and "multi-factor" in report_text
    finally:
        server.stop()
        await pool.close()
