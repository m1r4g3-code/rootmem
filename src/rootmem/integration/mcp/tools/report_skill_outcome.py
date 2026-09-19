"""`report_skill_outcome` — an explicit report that applying a skill or
lesson worked (or did not). Feeds the Beta posterior behind `find_skill`'s
trust term (ADR 0024). Explicit by design, never inferred (ADR 0014/0019)."""

from __future__ import annotations

from rootmem.extraction.contradiction import apply_evidence
from rootmem.integration.mcp.schemas import ReportSkillOutcomeParams, ReportSkillOutcomeResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.procedural_protocols import ProceduralMemoryRepository
from rootmem.trust.scoring import skill_effectiveness


@log_operation("report_skill_outcome")
async def report_skill_outcome(
    procedural_memory_repository: ProceduralMemoryRepository,
    params: ReportSkillOutcomeParams,
    reliability: float,
    prior_strength: float,
) -> ReportSkillOutcomeResult:
    # Evidence deltas from a zero belief: success adds weight to alpha,
    # failure to beta -- the same rule feedback uses for relations.
    delta_alpha, delta_beta = apply_evidence(
        0.0,
        0.0,
        confidence=1.0,
        reliability=reliability,
        prior_strength=prior_strength,
        supporting=params.success,
    )
    record = await procedural_memory_repository.record_outcome(
        params.namespace, params.name, params.success, delta_alpha, delta_beta
    )
    if record is None:
        return ReportSkillOutcomeResult(name=params.name, found=False)
    return ReportSkillOutcomeResult(
        name=record.name,
        found=True,
        applied_count=record.applied_count,
        success_count=record.success_count,
        effectiveness=skill_effectiveness(record.belief_alpha, record.belief_beta),
    )
