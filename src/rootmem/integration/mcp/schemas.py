"""MCP-facing request/response shapes for the 5 core tools.

Deliberately kept separate from `rootmem.storage.models.MemoryRecord` (see
that module's docstring) — a wire-format change here should never force a
storage-layer change, and vice versa. `MemoryView.from_record` is the one
place that bridges the two.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from rootmem.capture.models import IngestResult
from rootmem.storage.graph_models import RelationRecord
from rootmem.storage.models import MemoryRecord


def _reject_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


class MemoryView(BaseModel):
    """Public shape of a memory record returned to MCP clients."""

    id: str
    namespace: str
    key: str | None
    content: str
    source: str
    source_session_id: str | None
    confidence: float
    importance_flag: float
    salience_score: float | None
    consolidated_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: MemoryRecord) -> MemoryView:
        return cls(
            id=record.id,
            namespace=record.namespace,
            key=record.key,
            content=record.content,
            source=record.source,
            source_session_id=record.source_session_id,
            confidence=record.confidence,
            importance_flag=record.importance_flag,
            salience_score=record.salience_score,
            consolidated_at=record.consolidated_at,
            metadata=record.metadata,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


# --- remember ---------------------------------------------------------------


class RememberParams(BaseModel):
    content: str
    namespace: str = "default"
    key: str | None = None
    source: str
    source_session_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # Phase 2 (FR1, ADR 0016): a cheap, optional input to salience scoring,
    # applied at consolidation time -- no effect on remember's own latency.
    importance_flag: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> RememberParams:
        _reject_blank(self.content, "content")
        _reject_blank(self.source, "source")
        return self


class RememberResult(BaseModel):
    id: str
    created_at: datetime


# --- recall -------------------------------------------------------------------


class RecallParams(BaseModel):
    id: str | None = None
    key: str | None = None
    namespace: str = "default"

    @model_validator(mode="after")
    def _validate(self) -> RecallParams:
        if (self.id is None) == (self.key is None):
            raise ValueError("exactly one of 'id' or 'key' must be provided")
        return self


class RecallResult(BaseModel):
    found: bool
    record: MemoryView | None = None


# --- update -------------------------------------------------------------------


class UpdateParams(BaseModel):
    id: str
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate(self) -> UpdateParams:
        _reject_blank(self.id, "id")
        if self.content is not None:
            _reject_blank(self.content, "content")
        if self.content is None and self.confidence is None and self.metadata is None:
            raise ValueError("at least one of 'content', 'confidence', or 'metadata' is required")
        return self


class UpdateResult(BaseModel):
    id: str
    updated_at: datetime
    namespace: str


# --- forget -------------------------------------------------------------------


class ForgetParams(BaseModel):
    id: str
    reason: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> ForgetParams:
        _reject_blank(self.id, "id")
        return self


class ForgetResult(BaseModel):
    id: str
    deleted_at: datetime
    namespace: str


# --- search -------------------------------------------------------------------


class SearchParams(BaseModel):
    query: str
    namespace: str = "default"
    limit: int = Field(default=10, ge=1, le=50)
    source: str | None = None
    # "hybrid" (ADR 0007) is the default — a deliberate behavior change from
    # Phase 0's full-text-only search, since real semantic retrieval is the
    # whole point of this phase. "text" preserves the exact Phase 0 behavior.
    mode: Literal["text", "semantic", "hybrid"] = "hybrid"
    # Phase 4 (ADR 0022). Optional, explicit signals: naming an entity turns
    # on the graph_proximity term; `as_of` scores retention at that instant
    # (a what-if query, so it does not record access).
    entity_name: str | None = None
    entity_type: str | None = None
    as_of: datetime | None = None

    @model_validator(mode="after")
    def _validate(self) -> SearchParams:
        _reject_blank(self.query, "query")
        if (self.entity_name is None) != (self.entity_type is None):
            raise ValueError("entity_name and entity_type must be provided together")
        return self


class SearchResultItem(BaseModel):
    id: str
    content: str
    key: str | None
    score: float
    source: str
    created_at: datetime
    # Phase 4: per-term contribution to `score` (relevance, retention,
    # salience, trust, graph_proximity) when multi-factor ranking is active;
    # the values sum to `score`.
    breakdown: dict[str, float] | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


# --- related --------------------------------------------------------------


class RelatedParams(BaseModel):
    entity_name: str
    entity_type: str
    namespace: str = "default"
    max_hops: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def _validate(self) -> RelatedParams:
        _reject_blank(self.entity_name, "entity_name")
        _reject_blank(self.entity_type, "entity_type")
        return self


class RelationView(BaseModel):
    id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None
    object_literal: str | None
    confidence: float
    belief_alpha: float
    belief_beta: float
    valid_from: datetime
    valid_to: datetime | None
    is_active: bool
    is_contested: bool
    supersedes: str | None
    superseded_by: str | None
    derivation: Literal["extracted", "distilled"]
    # Populated separately from `relation_provenance` (not a RelationRecord
    # field -- provenance is a join table, one relation can have several
    # source episodes, especially after distillation). Empty list if the
    # caller (e.g. `related`) didn't look it up.
    source_memory_ids: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(
        cls, record: RelationRecord, source_memory_ids: list[str] | None = None
    ) -> RelationView:
        return cls(
            id=record.id,
            subject_entity_id=record.subject_entity_id,
            predicate=record.predicate,
            object_entity_id=record.object_entity_id,
            object_literal=record.object_literal,
            confidence=record.confidence,
            belief_alpha=record.belief_alpha,
            belief_beta=record.belief_beta,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            is_active=record.is_active,
            is_contested=record.is_contested,
            supersedes=record.supersedes,
            superseded_by=record.superseded_by,
            derivation=record.derivation,
            source_memory_ids=source_memory_ids or [],
        )


class RelatedResult(BaseModel):
    entity_found: bool
    entity_id: str | None = None
    relations: list[RelationView] = Field(default_factory=list)


# --- ingest_session ---------------------------------------------------------


class IngestSessionParams(BaseModel):
    transcript: str
    source: str
    namespace: str = "default"
    session_id: str | None = None
    importance_flag: float = Field(default=0.0, ge=0.0, le=1.0)
    # Phase 3 (FR1, ADR 0019): explicit, optional, agent-supplied signal for
    # episodic->procedural/failure->lesson distillation's session grouping --
    # never inferred from feedback or any other signal.
    session_outcome: Literal["success", "failure"] | None = None

    @model_validator(mode="after")
    def _validate(self) -> IngestSessionParams:
        _reject_blank(self.transcript, "transcript")
        _reject_blank(self.source, "source")
        return self


class IngestSessionResult(BaseModel):
    memory_id: str
    embedded: bool
    entities_extracted: int
    relations_extracted: int
    superseded_count: int
    contested_count: int
    extraction_degraded: bool

    @classmethod
    def from_ingest_result(cls, result: IngestResult) -> IngestSessionResult:
        return cls(**result.model_dump())


# --- consolidate --------------------------------------------------------------


class ConsolidateParams(BaseModel):
    namespace: str = "default"
    force: bool = False


class ConsolidateResult(BaseModel):
    ran: bool
    trigger_reason: Literal["count", "time", "manual"] | None = None
    episodes_processed: int = 0
    clusters_formed: int = 0
    facts_distilled: int = 0
    procedures_distilled: int = 0
    lessons_distilled: int = 0


# --- feedback -------------------------------------------------------------------


class FeedbackParams(BaseModel):
    relation_id: str
    namespace: str = "default"
    outcome: Literal["confirmed", "contradicted"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    note: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> FeedbackParams:
        _reject_blank(self.relation_id, "relation_id")
        return self


class FeedbackResult(BaseModel):
    relation: RelationView


# --- find_skill / get_skill (Phase 3, ADR 0017/0018) -------------------------


class FindSkillParams(BaseModel):
    query: str
    namespace: str = "default"
    kind: Literal["skill", "lesson", "all"] = "all"
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _validate(self) -> FindSkillParams:
        _reject_blank(self.query, "query")
        return self


class SkillSearchResultItem(BaseModel):
    name: str
    kind: Literal["skill", "lesson"]
    description: str
    score: float
    # Phase 4 (ADR 0024): posterior mean of "this works" and the per-term
    # breakdown of `score`, present when multi-factor ranking is active.
    effectiveness: float | None = None
    breakdown: dict[str, float] | None = None


class FindSkillResult(BaseModel):
    results: list[SkillSearchResultItem] = Field(default_factory=list)


class GetSkillParams(BaseModel):
    name: str
    namespace: str = "default"

    @model_validator(mode="after")
    def _validate(self) -> GetSkillParams:
        _reject_blank(self.name, "name")
        return self


class GetSkillResult(BaseModel):
    found: bool
    kind: Literal["skill", "lesson"] | None = None
    # Literal SKILL.md-conformant markdown text (ADR 0018) -- ROOTMEM's
    # entire contract for a skill ends here; installing it anywhere is the
    # calling agent's/human's job, not this server's.
    markdown: str | None = None


# --- report_skill_outcome (Phase 4, ADR 0024) -----------------------------------


class ReportSkillOutcomeParams(BaseModel):
    name: str
    namespace: str = "default"
    success: bool

    @model_validator(mode="after")
    def _validate(self) -> ReportSkillOutcomeParams:
        _reject_blank(self.name, "name")
        return self


class ReportSkillOutcomeResult(BaseModel):
    name: str
    found: bool
    applied_count: int = 0
    success_count: int = 0
    effectiveness: float | None = None


# --- verify_audit (Phase 4, ADR 0025) -------------------------------------------


class VerifyAuditParams(BaseModel):
    namespace: str = "default"


class VerifyAuditResult(BaseModel):
    valid: bool
    entries_checked: int
    first_broken_seq: int | None = None
    reason: str | None = None
    audit_enabled: bool = True
