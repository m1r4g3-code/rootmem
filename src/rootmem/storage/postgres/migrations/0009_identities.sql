-- yoyo-migrations: 0009_identities
-- depends: 0008_access_tracking_preserves_updated_at

-- Phase 5 (ADR 0027): an agent identity, referenced by a bearer token that is
-- stored only as its SHA-256 digest. `namespaces` lists what the identity may
-- access; revocation is a soft state (`revoked_at`), never a DELETE.
CREATE TABLE identities (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,
    token_sha256  TEXT NOT NULL UNIQUE,
    namespaces    TEXT[] NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at    TIMESTAMPTZ NULL,
    CONSTRAINT identities_name_nonempty CHECK (length(trim(name)) > 0),
    CONSTRAINT identities_has_namespace CHECK (cardinality(namespaces) > 0)
);
