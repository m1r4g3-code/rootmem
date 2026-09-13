"""Domain model for a stored memory record.

This is the internal representation shared by every `MemoryRepository`
implementation (in-memory fake, Postgres). MCP-facing request/response
shapes live separately in `rootmem.integration.mcp.schemas` — the two are
not the same type, so a wire-format change doesn't leak into storage code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = 1


class MemoryRecord(BaseModel):
    """A single memory row, forward-compatible with later phases.

    `content_embedding` is provisioned for Phase 1's semantic search but is
    always None in Phase 0 — nothing populates or queries it yet (see ADR
    on the unconstrained VECTOR column in the Phase 0 plan).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    schema_version: int = CURRENT_SCHEMA_VERSION

    namespace: str
    key: str | None = None
    idempotency_key: str | None = None

    content: str
    content_embedding: list[float] | None = None

    source: str
    source_session_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_reason: str | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class NewMemory(BaseModel):
    """Input to `MemoryRepository.create` — no id/timestamps, those are assigned by the store."""

    namespace: str
    key: str | None = None
    idempotency_key: str | None = None
    content: str
    source: str
    source_session_id: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    """Partial update to an existing record. Unset fields are left unchanged."""

    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] | None = None


class SearchResult(BaseModel):
    """One ranked hit from `MemoryRepository.search_text`."""

    record: MemoryRecord
    score: float
