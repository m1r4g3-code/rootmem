-- yoyo-migrations: 0001_init
-- depends:

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- pgvector has no simple Windows binary install (no official prebuilt
-- package; building it requires Visual Studio + PostgreSQL's dev headers).
-- The docker-compose Postgres image (pgvector/pgvector) has it baked in;
-- a native Windows Postgres install used as a stopgap while Docker/WSL2
-- is broken on this machine does not. Since Phase 0 never populates or
-- queries content_embedding anyway (see the schema's own comment below),
-- this migration degrades gracefully: it creates the extension and column
-- when available, and skips both — logging why — when not, so the same
-- migration file is correct against either backend without special-casing
-- environments at the application layer.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available; content_embedding column will be skipped (see migration comment)';
END $$;

CREATE TABLE memories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_version      SMALLINT NOT NULL DEFAULT 1,

    namespace           TEXT NOT NULL DEFAULT 'default',
    key                 TEXT NULL,
    idempotency_key     TEXT NULL,

    content             TEXT NOT NULL,

    source              TEXT NOT NULL,
    source_session_id   TEXT NULL,
    -- DOUBLE PRECISION, not REAL: REAL (float4) cannot exactly represent
    -- values like 0.9, so a round-trip through it silently corrupts
    -- confidence scores by a small but real amount (caught by the Postgres
    -- integration test suite, which the in-memory fake can't catch since
    -- Python floats are already double precision).
    confidence          DOUBLE PRECISION NOT NULL DEFAULT 1.0
                          CHECK (confidence >= 0 AND confidence <= 1),

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ NULL,
    deleted_reason      TEXT NULL,

    CONSTRAINT memories_content_nonempty CHECK (length(trim(content)) > 0)
);

-- content_embedding: dimension-unconstrained VECTOR, dark until Phase 1
-- fixes an embedding model and populates it — see the plan's "Vector
-- dimension" decision. Added conditionally: only present when the vector
-- extension actually loaded (see the DO block above).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        EXECUTE 'ALTER TABLE memories ADD COLUMN content_embedding VECTOR NULL';
    END IF;
END $$;

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
