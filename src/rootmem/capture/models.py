"""Domain model for the capture layer's output — what `ingest_transcript`
reports back, and what the `ingest_session` MCP tool's response is built
from (FR3, docs/requirements/phase1-requirements.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IngestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    embedded: bool
    entities_extracted: int
    relations_extracted: int
    superseded_count: int
    contested_count: int
    extraction_degraded: bool
