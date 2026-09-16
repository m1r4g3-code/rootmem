"""Domain model for LLM-based extraction output.

Deliberately a different shape from `storage.graph_models`: extraction
produces entity/relation *names* (strings), not entity ids — resolving a
name to an `EntityRecord.id` (via `GraphRepository.upsert_entity`) is
`extraction.pipeline`'s job, not the extraction provider's. This keeps
`ExtractionProvider` implementations ignorant of the graph store entirely
(layer isolation, ADR 0009).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ExtractionContext(BaseModel):
    """What the extraction provider needs to know about where this text
    came from — not what it's extracting from (that's `text`, passed
    separately to `ExtractionProvider.extract`)."""

    namespace: str
    source: str
    source_session_id: str | None = None


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str


class ExtractedRelation(BaseModel):
    """Mirrors `storage.graph_models.NewRelation`'s object-shape choice
    (entity-to-entity or a literal scalar), but by name, not id."""

    subject_name: str
    subject_type: str
    predicate: str
    object_name: str | None = None
    object_type: str | None = None
    object_literal: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _object_present_and_consistent(self) -> ExtractedRelation:
        if self.object_name is None and self.object_literal is None:
            raise ValueError("relation must have object_name or object_literal")
        if self.object_name is not None and self.object_type is None:
            raise ValueError("object_type is required when object_name is set")
        return self


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
