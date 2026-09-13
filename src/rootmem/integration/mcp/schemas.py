"""MCP-facing request/response shapes for the 5 core tools.

Deliberately kept separate from `rootmem.storage.models.MemoryRecord` (see
that module's docstring) — a wire-format change here should never force a
storage-layer change, and vice versa. `MemoryView.from_record` is the one
place that bridges the two.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

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


# --- search -------------------------------------------------------------------


class SearchParams(BaseModel):
    query: str
    namespace: str = "default"
    limit: int = Field(default=10, ge=1, le=50)
    source: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> SearchParams:
        _reject_blank(self.query, "query")
        return self


class SearchResultItem(BaseModel):
    id: str
    content: str
    key: str | None
    score: float
    source: str
    created_at: datetime


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
