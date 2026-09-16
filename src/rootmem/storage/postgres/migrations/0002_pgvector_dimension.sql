-- yoyo-migrations: 0002_pgvector_dimension
-- depends: 0001_init

-- Phase 1 makes pgvector a hard requirement (ADR 0007) — no more Phase 0's
-- graceful skip. IF NOT EXISTS makes this step idempotent (safe to retry
-- after a connection drop mid-migration) without weakening the
-- requirement: if pgvector genuinely isn't available, this still raises
-- the same error it always would (see docs/adr/0011 for how local dev
-- resolved this on a Windows machine with no VS C++ toolchain).
CREATE EXTENSION IF NOT EXISTS vector;

-- content_embedding may or may not already exist as an unconstrained VECTOR
-- column, depending on whether 0001_init ran against an instance that had
-- pgvector available at the time (see 0001's own conditional DO block).
-- Handle both cases so this migration is correct regardless of history.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'content_embedding'
    ) THEN
        -- Safe even with existing rows: NULL values cast to NULL, and
        -- Phase 0 never populated this column (dark by design), so there
        -- is nothing to lose in the cast.
        ALTER TABLE memories ALTER COLUMN content_embedding TYPE VECTOR(1024);
    ELSE
        ALTER TABLE memories ADD COLUMN content_embedding VECTOR(1024) NULL;
    END IF;
END $$;

-- HNSW, not ivfflat (ADR 0007): ivfflat's `lists` parameter needs tuning
-- against table size, which is meaningless for a table that starts empty.
CREATE INDEX ix_memories_embedding_hnsw
    ON memories USING hnsw (content_embedding vector_cosine_ops);
