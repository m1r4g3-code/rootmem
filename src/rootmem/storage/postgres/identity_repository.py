"""`asyncpg`-backed `IdentityRepository` (ADR 0027), backed by `identities`
(migration 0009)."""

from __future__ import annotations

import asyncpg

from rootmem.identity.models import Identity
from rootmem.storage.identity_protocols import IdentityExistsError
from rootmem.storage.protocols import StorageError

_COLUMNS = "id, name, namespaces, created_at, revoked_at"


def _row_to_identity(row: asyncpg.Record) -> Identity:
    return Identity(
        id=str(row["id"]),
        name=row["name"],
        namespaces=list(row["namespaces"]),
        created_at=row["created_at"],
        revoked_at=row["revoked_at"],
    )


class PostgresIdentityRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, name: str, namespaces: list[str], token_sha256: str) -> Identity:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO identities (name, namespaces, token_sha256)
                    VALUES ($1, $2, $3)
                    RETURNING {_COLUMNS}
                    """,
                    name,
                    namespaces,
                    token_sha256,
                )
        except asyncpg.UniqueViolationError as exc:
            raise IdentityExistsError(name) from exc
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to create identity: {exc}") from exc
        assert row is not None
        return _row_to_identity(row)

    async def get_by_token_hash(self, token_sha256: str) -> Identity | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT {_COLUMNS} FROM identities "
                    "WHERE token_sha256 = $1 AND revoked_at IS NULL",
                    token_sha256,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to look up identity: {exc}") from exc
        return _row_to_identity(row) if row is not None else None

    async def list_identities(self) -> list[Identity]:
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT {_COLUMNS} FROM identities ORDER BY created_at")
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to list identities: {exc}") from exc
        return [_row_to_identity(row) for row in rows]

    async def revoke(self, name: str) -> Identity | None:
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    UPDATE identities SET revoked_at = COALESCE(revoked_at, now())
                    WHERE name = $1
                    RETURNING {_COLUMNS}
                    """,
                    name,
                )
        except asyncpg.PostgresError as exc:
            raise StorageError(f"failed to revoke identity: {exc}") from exc
        return _row_to_identity(row) if row is not None else None
