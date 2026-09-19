-- yoyo-migrations: 0005_procedural_memory
-- depends: 0004_consolidation

-- Phase 3: procedural memory (skills) and failure->lesson distillation. See
-- docs/math-spec/phase3-math-spec.md for the session-trace clustering and
-- SKILL.md rendering derivation, and ADRs 0017-0021 for the design
-- rationale behind each piece below.

ALTER TABLE memories ADD COLUMN session_outcome TEXT NULL
    CHECK (session_outcome IN ('success', 'failure'));
-- Phase 3 (ADR 0019): explicit, agent-supplied, ingest_session-only signal --
-- the minimal new capture surface needed to group episodes into session
-- traces by outcome, reusing the already-existing source_session_id column
-- rather than inventing a new ordered-steps capture concept.

-- ProceduralMemoryRepository's own aggregate (ADR 0017) -- a distilled
-- skill/lesson artifact is neither a raw episode, a graph fact, nor a
-- consolidation run record.
CREATE TABLE procedural_memories (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace          TEXT NOT NULL,
    kind               TEXT NOT NULL CHECK (kind IN ('skill', 'lesson')),
    name               TEXT NOT NULL,       -- lowercase-hyphen slug, <=64 chars (agentskills.io)
    description        TEXT NOT NULL,       -- <=1024 chars, what+when (agentskills.io)
    body_markdown      TEXT NOT NULL,
    content_embedding  VECTOR(1024) NULL,   -- same voyage-4/1024 model as memories (ADR 0007)
    derivation         TEXT NOT NULL DEFAULT 'distilled' CHECK (derivation IN ('distilled')),
    supersedes         UUID NULL REFERENCES procedural_memories(id),
    superseded_by      UUID NULL REFERENCES procedural_memories(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ NULL,
    deleted_reason     TEXT NULL
);

-- Uniqueness only among active (non-superseded, non-deleted) rows -- a name
-- collision on re-distillation supersedes the old row (ADR 0004's
-- soft-delete philosophy extended, mirroring relations.supersedes/
-- superseded_by), never a hard UPDATE-in-place or DELETE.
CREATE UNIQUE INDEX ix_procedural_memories_active_name
    ON procedural_memories (namespace, name)
    WHERE superseded_by IS NULL AND deleted_at IS NULL;

CREATE INDEX ix_procedural_memories_embedding_hnsw
    ON procedural_memories USING hnsw (content_embedding vector_cosine_ops);

CREATE INDEX ix_procedural_memories_active_kind
    ON procedural_memories (namespace, kind)
    WHERE superseded_by IS NULL AND deleted_at IS NULL;

-- procedural_memory_provenance is relation_provenance's exact shape,
-- generalized to a different parent aggregate.
CREATE TABLE procedural_memory_provenance (
    procedural_memory_id UUID NOT NULL REFERENCES procedural_memories(id),
    memory_id            UUID NOT NULL REFERENCES memories(id),
    PRIMARY KEY (procedural_memory_id, memory_id)
);

ALTER TABLE consolidation_runs ADD COLUMN procedures_distilled INT NOT NULL DEFAULT 0;
ALTER TABLE consolidation_runs ADD COLUMN lessons_distilled    INT NOT NULL DEFAULT 0;
