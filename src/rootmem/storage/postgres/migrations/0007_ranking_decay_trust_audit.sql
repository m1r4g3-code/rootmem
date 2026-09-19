-- yoyo-migrations: 0007_ranking_decay_trust_audit
-- depends: 0006_procedural_memories_deferrable_supersede_fk

-- Phase 4 (ADRs 0022-0026).

-- Access tracking (ADR 0023): the input R(t) decay needs. Decay itself is
-- computed at read time and never rewrites or deletes anything.
ALTER TABLE memories ADD COLUMN last_accessed_at TIMESTAMPTZ NULL;
ALTER TABLE memories ADD COLUMN access_count INT NOT NULL DEFAULT 0 CHECK (access_count >= 0);
-- Memory trust (ADR 0024) is source reliability x confidence, both already
-- stored, so it is computed at rank time rather than cached in a column.

-- Skill/lesson effectiveness (ADR 0024): a Beta posterior over "this works",
-- fed only by the explicit report_skill_outcome tool.
ALTER TABLE procedural_memories ADD COLUMN belief_alpha DOUBLE PRECISION NOT NULL DEFAULT 1.0
    CHECK (belief_alpha > 0);
ALTER TABLE procedural_memories ADD COLUMN belief_beta DOUBLE PRECISION NOT NULL DEFAULT 1.0
    CHECK (belief_beta > 0);
ALTER TABLE procedural_memories ADD COLUMN applied_count INT NOT NULL DEFAULT 0
    CHECK (applied_count >= 0);
ALTER TABLE procedural_memories ADD COLUMN success_count INT NOT NULL DEFAULT 0
    CHECK (success_count >= 0);

-- Tamper-evident audit log (ADR 0025): append-only, one hash chain per
-- namespace. row_hash = SHA-256(prev_hash || canonical row JSON), computed
-- in application code (rootmem.audit.chain) so the DB and the in-memory
-- fake share one definition.
CREATE TABLE audit_log (
    namespace    TEXT NOT NULL,
    seq          BIGINT NOT NULL CHECK (seq >= 1),
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT NULL,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL,
    prev_hash    TEXT NOT NULL,
    row_hash     TEXT NOT NULL,
    PRIMARY KEY (namespace, seq)
);

CREATE FUNCTION audit_log_reject_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_reject_mutation();
