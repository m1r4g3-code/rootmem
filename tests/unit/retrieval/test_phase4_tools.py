"""Phase 4 tool handlers (recall access tracking, find_skill re-rank,
report_skill_outcome, verify_audit) against the in-memory fakes."""

from __future__ import annotations

import pytest

from rootmem.audit.recorder import AuditRecorder, content_sha256
from rootmem.config import Settings
from rootmem.embedding.protocols import EmbeddingError
from rootmem.integration.mcp.schemas import (
    FindSkillParams,
    RecallParams,
    ReportSkillOutcomeParams,
    VerifyAuditParams,
)
from rootmem.integration.mcp.tools.find_skill import find_skill
from rootmem.integration.mcp.tools.recall import recall
from rootmem.integration.mcp.tools.report_skill_outcome import report_skill_outcome
from rootmem.integration.mcp.tools.verify_audit import verify_audit
from rootmem.retrieval.rerank import RankingContext
from rootmem.storage.fakes.in_memory_audit_repository import InMemoryAuditLogRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.models import NewMemory
from rootmem.storage.procedural_protocols import NewProceduralMemory


class _NoEmbeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("embeddings unavailable")


async def test_recall_records_access() -> None:
    repo = InMemoryMemoryRepository()
    created = await repo.create(NewMemory(namespace="ns", content="hello", source="t"))

    await recall(repo, RecallParams(id=created.id, namespace="ns"))
    await recall(repo, RecallParams(id=created.id, namespace="ns"))

    fetched = await repo.get_by_id("ns", created.id)
    assert fetched is not None and fetched.access_count == 2


async def test_recall_of_missing_memory_is_not_an_error() -> None:
    repo = InMemoryMemoryRepository()
    result = await recall(repo, RecallParams(id="00000000-0000-0000-0000-000000000000"))
    assert result.found is False


async def test_skill_with_reported_successes_outranks_one_with_failures() -> None:
    procedural = InMemoryProceduralMemoryRepository()
    for name in ("deploy-guide-a", "deploy-guide-b"):
        await procedural.create(
            NewProceduralMemory(
                namespace="ns",
                kind="skill",
                name=name,
                description="how to deploy the service safely",
                body_markdown="steps",
            )
        )
    settings = Settings()
    for _ in range(3):
        await report_skill_outcome(
            procedural,
            ReportSkillOutcomeParams(name="deploy-guide-a", namespace="ns", success=True),
            settings.bayesian_source_reliability_feedback,
            settings.bayesian_prior_strength,
        )
        await report_skill_outcome(
            procedural,
            ReportSkillOutcomeParams(name="deploy-guide-b", namespace="ns", success=False),
            settings.bayesian_source_reliability_feedback,
            settings.bayesian_prior_strength,
        )

    result = await find_skill(
        procedural,
        _NoEmbeddings(),
        FindSkillParams(query="deploy the service", namespace="ns"),
        ranking=RankingContext.from_settings(settings),
    )

    assert [item.name for item in result.results] == ["deploy-guide-a", "deploy-guide-b"]
    assert result.results[0].effectiveness is not None
    assert result.results[1].effectiveness is not None
    assert result.results[0].effectiveness > 0.5 > result.results[1].effectiveness
    assert result.results[0].breakdown is not None


async def test_report_skill_outcome_unknown_skill_is_not_found() -> None:
    procedural = InMemoryProceduralMemoryRepository()
    result = await report_skill_outcome(
        procedural,
        ReportSkillOutcomeParams(name="nope", namespace="ns", success=True),
        1.0,
        2.0,
    )
    assert result.found is False


async def test_verify_audit_detects_tampering() -> None:
    audit_repo = InMemoryAuditLogRepository()
    recorder = AuditRecorder(audit_repo, "tester")
    for i in range(3):
        await recorder.record("ns", "remember", "memory", f"m{i}", {"h": content_sha256(str(i))})

    intact = await verify_audit(audit_repo, VerifyAuditParams(namespace="ns"))
    assert intact.valid is True and intact.entries_checked == 3

    audit_repo.tamper_for_test("ns", 1, {"h": "forged"})
    broken = await verify_audit(audit_repo, VerifyAuditParams(namespace="ns"))
    assert broken.valid is False
    assert broken.first_broken_seq == 2


async def test_verify_audit_without_a_store_reports_disabled() -> None:
    result = await verify_audit(None, VerifyAuditParams(namespace="ns"))
    assert result.audit_enabled is False


async def test_recorder_without_a_repository_is_a_noop() -> None:
    recorder = AuditRecorder(None, "tester")
    assert recorder.enabled is False
    await recorder.record("ns", "remember", "memory", "m1")


def test_content_digest_is_stable_and_not_the_content() -> None:
    digest = content_sha256("secret text")
    assert digest == content_sha256("secret text")
    assert "secret" not in digest
    assert len(digest) == 64


@pytest.mark.parametrize("bad", ["", "   "])
def test_report_skill_outcome_rejects_blank_name(bad: str) -> None:
    with pytest.raises(ValueError):
        ReportSkillOutcomeParams(name=bad, success=True)
