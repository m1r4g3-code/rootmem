# ADR 0031: Integration tests run against a separate database, guarded against truncating any other

**Status:** Accepted
**Date:** 2026-09-19

## Context

Four integration fixtures `TRUNCATE` tables in the one configured database, which is also the live/manual one. Phase 4's manual checks lost data twice, and a concurrent run corrupted an exit-test run.

## Decision

Integration tests connect to `POSTGRES_TEST_DB` (default `<db>_test`). A shared guard refuses any `TRUNCATE` unless the connected database name ends in `_test`. `scripts/create_test_db.py` creates the database, enables `vector`/`pgcrypto`, and applies migrations. CI already uses a throwaway container and only needs the name to match.

## Alternatives considered

- Per-test schemas: rejected, extension and search-path handling adds risk.
- Scoped deletes everywhere: rejected, several tests need clean tables.

## Consequences

Local integration runs need the test database created once. Live/manual work on the main database is no longer at risk from test runs.
