-- yoyo-migrations: 0003_graph_tables
-- depends: 0002_pgvector_dimension

-- Bi-temporal semantic graph as plain Postgres tables, not a dedicated
-- graph engine — see ADR 0006 (supersedes ADR 0001). valid_from/valid_to
-- is valid time (when the fact was/is true in the world); recorded_at is
-- transaction time (when this system learned it) — the same split
-- Zep/Graphiti publishes for bi-temporal edge modeling, adapted to plain
-- Postgres tables rather than their dedicated graph backend (see
-- docs/research/phase1-research-memo.md).

CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    name            TEXT NOT NULL,
    -- normalized(name): Phase 1's deliberately minimal dedup (ADR — see the
    -- research memo's "sophisticated entity resolution" open item). No
    -- coreference/fuzzy matching; exact match on the normalized form only.
    canonical_key   TEXT NOT NULL,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (namespace, entity_type, canonical_key)
);

CREATE TRIGGER trg_entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE relations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace           TEXT NOT NULL,

    subject_entity_id   UUID NOT NULL REFERENCES entities(id),
    predicate           TEXT NOT NULL,
    object_entity_id    UUID NULL REFERENCES entities(id),
    -- Escape hatch for scalar facts (e.g. "Alice's favorite color is blue")
    -- that don't warrant modeling the object as its own entity — a Phase 1
    -- simplification traded against a cleaner pure-property-graph model
    -- (see the research memo's "relation object modeling" open item).
    object_literal      TEXT NULL,

    -- DOUBLE PRECISION, not REAL — Phase 0 already paid for this lesson
    -- once (see docs/adr/0004 and scripts/manual_recall_check.md's
    -- native-Postgres validation retro); not repeating it here.
    confidence          DOUBLE PRECISION NOT NULL DEFAULT 1.0
                          CHECK (confidence >= 0 AND confidence <= 1),

    valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),  -- valid time
    valid_to            TIMESTAMPTZ NULL,                    -- NULL = currently active
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),  -- transaction time

    -- Contradiction resolution (ADR 0008) never deletes a row: the loser
    -- gets valid_to + superseded_by set, the winner gets supersedes set —
    -- extending ADR 0004's soft-delete discipline to the graph layer.
    supersedes          UUID NULL REFERENCES relations(id),
    superseded_by        UUID NULL REFERENCES relations(id),

    source_memory_id    UUID NULL REFERENCES memories(id),

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT relations_object_present
        CHECK (object_entity_id IS NOT NULL OR object_literal IS NOT NULL)
);

-- The index the exit criterion's contradiction-detection query relies on:
-- "is there already an active relation for this (namespace, subject,
-- predicate)?"
CREATE INDEX ix_relations_active
    ON relations (namespace, subject_entity_id, predicate)
    WHERE valid_to IS NULL;

CREATE INDEX ix_relations_source_memory
    ON relations (source_memory_id)
    WHERE source_memory_id IS NOT NULL;

-- Join table: which memories an entity was extracted from. Many-to-many —
-- one memory can mention several entities, one entity can be mentioned by
-- several memories.
CREATE TABLE memory_entities (
    memory_id   UUID NOT NULL REFERENCES memories(id),
    entity_id   UUID NOT NULL REFERENCES entities(id),
    PRIMARY KEY (memory_id, entity_id)
);
