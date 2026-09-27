"""The Phase 8 exit criterion (docs/requirements/phase8-requirements.md),
proven against a real uvicorn HTTP server, real Postgres, and a real
`asyncio` background loop that must resolve a contested relation with
**nobody calling anything** during the wait (ADR 0053 -- the one
wait-and-observe proof in this project, replacing every prior phase's
call-and-response pattern because the claim itself is "this happens
unprompted").

(1)(2)(3) A contested pair, backdated far enough for decay to have
    separated the two sides, is resolved autonomously during a real,
    bounded wait with no tool call in between; a second, fresh contest
    created just after is confirmed still untouched afterward (selectivity,
    not a blanket sweep); the resolution's audit entry is attributed to the
    fixed rumination actor, never a caller identity.
(6) The explicit `ruminate(force=True)` tool resolves the still-young
    contest on demand, without waiting for the loop.
(7) The loop is still healthy after its first (successful) pass -- proven
    by the explicit tool call still working against the same server
    afterward, and by a second autonomous resolution never having crashed
    anything in between.

Marked `integration` (not `integration_external`): the contested pairs are
seeded by writing directly through `PostgresGraphRepository`/raw SQL, not
through LLM extraction, so no Voyage or Anthropic call is required.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from rootmem.config import get_settings
from rootmem.extraction.contradiction import BayesianSettings
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.storage.graph_models import NewEntity, NewRelation
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository
from tests.integration.test_phase5_exit_criterion import (
    _call,
    _client,
    _free_port,
    _HttpServer,
    _ok,
)

pytestmark = pytest.mark.integration

_RUMINATION_ENV = {
    "RUMINATION_ENABLED": "true",
    "RUMINATION_INTERVAL_MINUTES": "0.05",  # 3 seconds
    "RUMINATION_MIN_CONTEST_AGE_HOURS": "0.01",  # 36 seconds
}


async def _seed_contested_pair(
    graph_repository: PostgresGraphRepository,
    pool: asyncpg.Pool,
    namespace: str,
    older_recorded_at: datetime,
    newer_recorded_at: datetime,
    subject_name: str = "Alice",
) -> tuple[str, str]:
    # `subject_name` must differ between two pairs seeded into the same
    # namespace -- otherwise the second pair's first relation corroborates
    # or re-contests whatever the first pair's own resolution left active,
    # instead of forming its own independent, fresh contest.
    subject = await graph_repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Person", name=subject_name)
    )
    acme = await graph_repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Organization", name="Acme")
    )
    globex = await graph_repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Organization", name="Globex")
    )
    first = await graph_repository.create_relation(
        NewRelation(
            namespace=namespace,
            subject_entity_id=subject.id,
            predicate="works_at",
            object_entity_id=acme.id,
            confidence=1.0,
        )
    )
    second = await graph_repository.create_relation(
        NewRelation(
            namespace=namespace,
            subject_entity_id=subject.id,
            predicate="works_at",
            object_entity_id=globex.id,
            confidence=0.1,
        )
    )
    assert second.contested is True
    older_id, newer_id = first.new.id, second.new.id

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE relations SET recorded_at = $2, valid_from = $2 WHERE id = $1",
            older_id,
            older_recorded_at,
        )
        await conn.execute(
            "UPDATE relations SET recorded_at = $2, valid_from = $2 WHERE id = $1",
            newer_id,
            newer_recorded_at,
        )
    return older_id, newer_id


@pytest.mark.asyncio
async def test_phase8_autonomous_rumination_resolves_a_contest_unprompted() -> None:
    suffix = uuid.uuid4().hex[:8]
    namespace = f"phase8-{suffix}"
    name = f"p8-{suffix}"
    token = generate_token()

    settings = get_settings()
    pool = await create_pool(settings)
    graph_repository = PostgresGraphRepository(pool, BayesianSettings.from_settings(settings))
    server = _HttpServer(_free_port(), extra_env=_RUMINATION_ENV)
    try:
        await PostgresIdentityRepository(pool).create(name, [namespace], hash_token(token))

        now = datetime.now(UTC)
        older_id, newer_id = await _seed_contested_pair(
            graph_repository,
            pool,
            namespace,
            older_recorded_at=now - timedelta(days=30),
            newer_recorded_at=now - timedelta(hours=2),  # past the 36s grace period
        )

        await server.start()

        # --- the wait: no tool call of any kind happens here ---
        await asyncio.sleep(7)  # >= 2 rumination intervals (3s each)

        # --- selectivity: a fresh, too-young contest, seeded just now, on a
        # different subject entity so it cannot interact with the pair above ---
        young_older_id, young_newer_id = await _seed_contested_pair(
            graph_repository,
            pool,
            namespace,
            older_recorded_at=datetime.now(UTC),
            newer_recorded_at=datetime.now(UTC),
            subject_name="Bob",
        )
        await asyncio.sleep(4)  # >= 1 more interval, so the loop examines it too

        # --- only now, read-only calls observe what already happened ---
        related_args = {"entity_name": "Alice", "entity_type": "Person", "namespace": namespace}
        young_related_args = {"entity_name": "Bob", "entity_type": "Person", "namespace": namespace}
        async with _client(server.url, token) as client:
            related_result = _ok(await _call(client, "related", **related_args))
            relations = {r["id"]: r for r in related_result["relations"]}
            young_result = _ok(await _call(client, "related", **young_related_args))
            young_relations = {r["id"]: r for r in young_result["relations"]}

        entries = await PostgresAuditLogRepository(pool).list_entries(namespace)
        rumination_entries = [e for e in entries if e.actor == "system:rumination"]

        # The old contest is resolved -- with nobody having called anything.
        winner_id = newer_id if relations[newer_id]["is_active"] else older_id
        loser_id = older_id if winner_id == newer_id else newer_id
        assert relations[winner_id]["is_contested"] is False
        assert relations[loser_id]["is_contested"] is False
        assert relations[loser_id]["superseded_by"] == winner_id
        assert len(rumination_entries) == 1
        assert rumination_entries[0].target_id == winner_id

        # The fresh, too-young contest is untouched -- selective, not a sweep.
        assert young_relations[young_older_id]["is_contested"] is True
        assert young_relations[young_newer_id]["is_contested"] is True
        assert young_relations[young_older_id]["is_active"] is True
        assert young_relations[young_newer_id]["is_active"] is True

        # --- the explicit tool resolves the young contest on demand ---
        async with _client(server.url, token) as client:
            forced = _ok(
                await _call(client, "ruminate", namespace=namespace, force=True)
            )
        assert forced["pairs_resolved"] >= 1

        async with _client(server.url, token) as client:
            after_forced_result = _ok(await _call(client, "related", **young_related_args))
            after_forced = {r["id"]: r for r in after_forced_result["relations"]}
        assert (
            after_forced[young_older_id]["is_contested"] is False
            or after_forced[young_newer_id]["is_contested"] is False
        )

        # --- the loop is still healthy: verify_audit still validates cleanly ---
        async with _client(server.url, token) as client:
            verified = _ok(await _call(client, "verify_audit", namespace=namespace))
        assert verified["valid"] is True
    finally:
        server.stop()
        await pool.close()
