-- yoyo-migrations: 0004_consolidation
-- depends: 0003_graph_tables

-- Phase 2: consolidation, salience, and the Bayesian belief update
-- replacing ADR 0008's deterministic contradiction rule. See
-- docs/math-spec/phase2-math-spec.md for the full derivation and
-- ADRs 0013/0015/0016 for the design rationale behind each piece below.

ALTER TABLE memories ADD COLUMN salience_score DOUBLE PRECISION NULL;
-- NULL until an episode has actually been through a consolidation pass
-- (ADR 0016) -- a normal, expected state, not an error condition.

ALTER TABLE memories ADD COLUMN importance_flag DOUBLE PRECISION NOT NULL DEFAULT 0.0
    CHECK (importance_flag >= 0 AND importance_flag <= 1);

ALTER TABLE memories ADD COLUMN consolidated_at TIMESTAMPTZ NULL;

-- Feeds MemoryRepository.count_unconsolidated/list_unconsolidated -- the
-- exact set of rows a consolidation pass needs to fetch.
CREATE INDEX ix_memories_unconsolidated ON memories (namespace, created_at)
    WHERE deleted_at IS NULL AND consolidated_at IS NULL;

ALTER TABLE relations ADD COLUMN derivation TEXT NOT NULL DEFAULT 'extracted'
    CHECK (derivation IN ('extracted', 'distilled'));

-- Beta-Bernoulli belief state (ADR 0013). `confidence` remains the fast-read
-- column every existing consumer (search, related, contradiction detection)
-- already uses; it is a cached function of these two, recomputed in the
-- same statement on every evidence update -- never independently assigned
-- by a caller. Beta(1,1) is the uniform prior a brand-new relation starts
-- from before any evidence is applied.
ALTER TABLE relations ADD COLUMN belief_alpha DOUBLE PRECISION NOT NULL DEFAULT 1.0
    CHECK (belief_alpha > 0);
ALTER TABLE relations ADD COLUMN belief_beta DOUBLE PRECISION NOT NULL DEFAULT 1.0
    CHECK (belief_beta > 0);

-- memory_entities-style provenance, generalized to relations that may be
-- derived from more than one source episode (distillation clusters several
-- episodes into one relation; extraction still uses exactly one, via the
-- existing relations.source_memory_id column, unchanged).
CREATE TABLE relation_provenance (
    relation_id UUID NOT NULL REFERENCES relations(id),
    memory_id   UUID NOT NULL REFERENCES memories(id),
    PRIMARY KEY (relation_id, memory_id)
);

-- A plain evidence-event log the Bayesian update writes to and could replay
-- from -- NOT the Phase 4 tamper-evident audit log (no hash-chaining or
-- signing here; see docs/requirements/phase2-requirements.md's non-goals).
CREATE TABLE relation_feedback (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    relation_id          UUID NOT NULL REFERENCES relations(id),
    namespace            TEXT NOT NULL,
    outcome              TEXT NOT NULL CHECK (outcome IN ('confirmed', 'contradicted')),
    reported_confidence  DOUBLE PRECISION NOT NULL DEFAULT 1.0
                           CHECK (reported_confidence >= 0 AND reported_confidence <= 1),
    note                 TEXT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_relation_feedback_relation ON relation_feedback (relation_id);

-- ConsolidationRepository's own aggregate (ADR 0016) -- a consolidation run
-- is neither a memory nor a relation, it is a record of when the system did
-- background work.
CREATE TABLE consolidation_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace           TEXT NOT NULL,
    trigger_reason      TEXT NOT NULL CHECK (trigger_reason IN ('count', 'time', 'manual')),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ NULL,
    episodes_processed  INT NOT NULL DEFAULT 0,
    clusters_formed     INT NOT NULL DEFAULT 0,
    facts_distilled     INT NOT NULL DEFAULT 0
);

CREATE INDEX ix_consolidation_runs_namespace ON consolidation_runs (namespace, started_at DESC);
