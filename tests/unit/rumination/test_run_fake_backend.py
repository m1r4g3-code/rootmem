from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rootmem.audit.recorder import AuditRecorder
from rootmem.rumination.run import RUMINATION_ACTOR, run_rumination_pass
from rootmem.storage.fakes.in_memory_audit_repository import InMemoryAuditLogRepository
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.graph_models import NewEntity, NewRelation, RelationRecord


async def _seed_contested_pair(
    repository: InMemoryGraphRepository,
    namespace: str,
    older_recorded_at: datetime,
    newer_recorded_at: datetime,
) -> tuple[str, str]:
    alice = await repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Person", name="Alice")
    )
    acme = await repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Organization", name="Acme")
    )
    globex = await repository.upsert_entity(
        NewEntity(namespace=namespace, entity_type="Organization", name="Globex")
    )
    first = await repository.create_relation(
        NewRelation(
            namespace=namespace,
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=acme.id,
            confidence=1.0,
        )
    )
    second = await repository.create_relation(
        NewRelation(
            namespace=namespace,
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=globex.id,
            confidence=0.1,
        )
    )
    assert second.contested is True
    older_id, newer_id = first.new.id, second.new.id
    # Backdate both directly -- a test-only, direct-repository step (the
    # same technique the exit-criterion test uses for real Postgres),
    # standing in for real elapsed time. `create_relation` always stamps
    # real wall-clock time internally (no injectable clock), so both sides
    # need explicit, controlled timestamps relative to the caller's own
    # `now` -- not just the older one -- or the age-gate check below reads
    # a near-zero real elapsed time no matter how far back `older` is set.
    repository._relations[older_id] = repository._relations[older_id].model_copy(  # noqa: SLF001
        update={"recorded_at": older_recorded_at, "valid_from": older_recorded_at}
    )
    repository._relations[newer_id] = repository._relations[newer_id].model_copy(  # noqa: SLF001
        update={"recorded_at": newer_recorded_at, "valid_from": newer_recorded_at}
    )
    return older_id, newer_id


@pytest.mark.asyncio
async def test_pass_resolves_a_contest_once_it_is_old_enough_and_decayed() -> None:
    repository = InMemoryGraphRepository()
    audit_repo = InMemoryAuditLogRepository()
    recorder = AuditRecorder(audit_repo, RUMINATION_ACTOR)
    now = datetime.now(UTC)
    older_id, newer_id = await _seed_contested_pair(
        repository,
        "ns",
        older_recorded_at=now - timedelta(days=30),
        newer_recorded_at=now - timedelta(hours=2),  # past the 1-hour grace period
    )

    summary = await run_rumination_pass(
        repository,
        recorder,
        now=now,
        namespace=None,
        decay_base_stability_days=7.0,
        supersede_margin=0.05,
        min_contest_age_hours=1.0,
    )

    assert summary.pairs_examined == 1
    assert summary.pairs_resolved == 1
    assert summary.pairs_skipped_too_young == 0
    assert summary.pairs_skipped_ambiguous == 0
    winner = await repository.get_relation_by_id("ns", newer_id)
    loser = await repository.get_relation_by_id("ns", older_id)
    assert winner is not None and not winner.is_contested
    assert loser is not None and loser.superseded_by == newer_id

    entries = await audit_repo.list_entries("ns")
    assert len(entries) == 1
    assert entries[0].actor == RUMINATION_ACTOR
    assert entries[0].action == "ruminate_resolve"
    assert entries[0].target_id == newer_id


@pytest.mark.asyncio
async def test_too_young_contest_is_skipped_unless_forced() -> None:
    repository = InMemoryGraphRepository()
    recorder = AuditRecorder(None, RUMINATION_ACTOR)
    now = datetime.now(UTC)
    # Both sides recorded "now" -- well within the grace period.
    older_id, newer_id = await _seed_contested_pair(
        repository, "ns", older_recorded_at=now, newer_recorded_at=now
    )

    summary = await run_rumination_pass(
        repository,
        recorder,
        now=now,
        namespace=None,
        decay_base_stability_days=7.0,
        supersede_margin=0.05,
        min_contest_age_hours=1.0,
    )
    assert summary.pairs_skipped_too_young == 1
    assert summary.pairs_resolved == 0
    still_contested = await repository.get_relation_by_id("ns", newer_id)
    assert still_contested is not None and still_contested.is_contested

    forced = await run_rumination_pass(
        repository,
        recorder,
        now=now,
        namespace=None,
        decay_base_stability_days=7.0,
        supersede_margin=0.05,
        min_contest_age_hours=1.0,
        force=True,
    )
    assert forced.pairs_examined == 1
    # Both recorded at the same instant -> decayed confidences differ only
    # by the raw belief gap (0.1 confidence vs 1.0), well past the margin.
    assert forced.pairs_resolved == 1
    assert older_id  # keeps the older id referenced, matching the pair helper


@pytest.mark.asyncio
async def test_namespace_scoped_pass_ignores_other_namespaces() -> None:
    repository = InMemoryGraphRepository()
    recorder = AuditRecorder(None, RUMINATION_ACTOR)
    now = datetime.now(UTC)
    older_at, newer_at = now - timedelta(days=30), now - timedelta(hours=2)
    await _seed_contested_pair(
        repository, "ns-a", older_recorded_at=older_at, newer_recorded_at=newer_at
    )
    await _seed_contested_pair(
        repository, "ns-b", older_recorded_at=older_at, newer_recorded_at=newer_at
    )

    summary = await run_rumination_pass(
        repository,
        recorder,
        now=now,
        namespace="ns-a",
        decay_base_stability_days=7.0,
        supersede_margin=0.05,
        min_contest_age_hours=1.0,
    )

    assert summary.pairs_examined == 1
    assert summary.pairs_resolved == 1
    remaining = await repository.list_contested("ns-b")
    assert len(remaining) == 2  # untouched


@pytest.mark.asyncio
async def test_three_way_contest_is_skipped_as_ambiguous() -> None:
    repository = InMemoryGraphRepository()
    recorder = AuditRecorder(None, RUMINATION_ACTOR)
    alice = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Person", name="Alice")
    )
    acme = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Acme")
    )
    globex = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Globex")
    )
    initech = await repository.upsert_entity(
        NewEntity(namespace="ns", entity_type="Organization", name="Initech")
    )
    await repository.create_relation(
        NewRelation(
            namespace="ns",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=acme.id,
            confidence=1.0,
        )
    )
    await repository.create_relation(
        NewRelation(
            namespace="ns",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=globex.id,
            confidence=0.1,
        )
    )
    await repository.create_relation(
        NewRelation(
            namespace="ns",
            subject_entity_id=alice.id,
            predicate="works_at",
            object_entity_id=initech.id,
            confidence=0.1,
        )
    )
    assert len(await repository.list_contested("ns")) == 3

    summary = await run_rumination_pass(
        repository,
        recorder,
        now=datetime.now(UTC),
        namespace="ns",
        decay_base_stability_days=7.0,
        supersede_margin=0.05,
        min_contest_age_hours=1.0,
        force=True,
    )
    assert summary.pairs_skipped_ambiguous == 1
    assert summary.pairs_resolved == 0


@pytest.mark.asyncio
async def test_a_failing_repository_is_reported_not_raised_by_the_caller() -> None:
    """The pure orchestration function itself propagates errors (NFR3's
    "never crashes the loop" guarantee lives in `rumination.loop`, which
    catches around this call) -- this just confirms nothing here swallows
    real repository errors silently."""

    class _Failing(InMemoryGraphRepository):
        async def list_contested(self, namespace: str | None) -> list[RelationRecord]:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await run_rumination_pass(
            _Failing(),
            AuditRecorder(None, RUMINATION_ACTOR),
            now=datetime.now(UTC),
            namespace=None,
            decay_base_stability_days=7.0,
            supersede_margin=0.05,
            min_contest_age_hours=1.0,
        )
