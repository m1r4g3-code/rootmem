-- yoyo-migrations: 0006_procedural_memories_deferrable_supersede_fk
-- depends: 0005_procedural_memory

-- Fixes a real bug found by Phase 3's own real-Postgres integration testing
-- (the exact "contract-test parity catches a real bug" pattern this project
-- has now hit in every phase): ProceduralMemoryRepository.create's supersede
-- swap needs to (a) mark the previous active row's superseded_by before the
-- new row exists, so the previous row drops out of
-- ix_procedural_memories_active_name's partial-unique membership before the
-- new row with the same (namespace, name) is inserted, while (b) superseded_by
-- has a foreign key to procedural_memories(id) that would otherwise reject
-- referencing a row that doesn't exist yet at that exact statement. Making
-- the FK DEFERRABLE INITIALLY DEFERRED lets the check happen at COMMIT time,
-- by which point the new row has been inserted -- both constraints are
-- satisfiable in the same transaction with no ordering conflict.

ALTER TABLE procedural_memories DROP CONSTRAINT procedural_memories_superseded_by_fkey;
ALTER TABLE procedural_memories
    ADD CONSTRAINT procedural_memories_superseded_by_fkey
    FOREIGN KEY (superseded_by) REFERENCES procedural_memories(id)
    DEFERRABLE INITIALLY DEFERRED;
