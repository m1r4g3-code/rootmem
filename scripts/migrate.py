#!/usr/bin/env python
"""Apply all pending Postgres migrations via yoyo-migrations.

Each migration runs inside its own transaction and yoyo tracks applied
migrations in its own table (`_yoyo_migration`), so a failed migration
rolls back cleanly and this script exits non-zero without leaving the
schema half-applied — see the Phase 0 plan's Hardening section.

Usage:
    uv run python scripts/migrate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from yoyo import get_backend, read_migrations

from rootmem.config import get_settings

_STORAGE_DIR = Path(__file__).parent.parent / "src" / "rootmem" / "storage"
MIGRATIONS_DIR = _STORAGE_DIR / "postgres" / "migrations"


def main() -> int:
    settings = get_settings()
    backend = get_backend(settings.postgres_dsn)
    migrations = read_migrations(str(MIGRATIONS_DIR))

    with backend.lock():
        to_apply = backend.to_apply(migrations)
        if not to_apply:
            print("No pending migrations.")
            return 0
        for migration in to_apply:
            print(f"Applying {migration.id}...")
        backend.apply_migrations(to_apply)
        print(f"Applied {len(to_apply)} migration(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
