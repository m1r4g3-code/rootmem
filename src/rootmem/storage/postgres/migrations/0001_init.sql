-- yoyo-migrations: 0001_init
-- depends:

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE memories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_version      SMALLINT NOT NULL DEFAULT 1,

    namespace           TEXT NOT NULL DEFAULT 'default',
    key                 TEXT NULL,
    idempotency_key     TEXT NULL,

    content             TEXT NOT NULL,
    content_embedding   VECTOR NULL,

    source              TEXT NOT NULL,
    source_session_id   TEXT NULL,
    confidence          REAL NOT NULL DEFAULT 1.0
                          CHECK (confidence >= 0 AND confidence <= 1),

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ NULL,
    deleted_reason      TEXT NULL,

    CONSTRAINT memories_content_nonempty CHECK (length(trim(content)) > 0)
);

CREATE UNIQUE INDEX ux_memories_namespace_idempotency
    ON memories (namespace, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX ix_memories_namespace_key
    ON memories (namespace, key)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_memories_active
    ON memories (namespace)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_memories_fulltext
    ON memories USING GIN (to_tsvector('english', content));

-- Vector index (ivfflat/hnsw) deferred to the Phase 1 migration that first
-- fixes content_embedding's dimension and populates it (see ADR discussion
-- in docs/adr and the Phase 0 plan's "Vector dimension" decision).

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
