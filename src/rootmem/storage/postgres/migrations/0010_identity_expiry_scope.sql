-- yoyo-migrations: 0010_identity_expiry_scope
-- depends: 0009_identities

-- Phase 6 (ADR 0033, 0034): optional token expiry, and a coarse scope.
-- Existing identities keep working unchanged: no expiry, readwrite.
ALTER TABLE identities ADD COLUMN expires_at TIMESTAMPTZ NULL;
ALTER TABLE identities ADD COLUMN scope TEXT NOT NULL DEFAULT 'readwrite'
    CHECK (scope IN ('read', 'readwrite'));
