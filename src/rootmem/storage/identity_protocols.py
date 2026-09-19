"""The identity storage port: `IdentityRepository` (ADR 0027).

A separate aggregate from memories, relations and audit entries. There is
deliberately no way to read a token back: only its SHA-256 digest is stored.
"""

from __future__ import annotations

from typing import Protocol

from rootmem.identity.models import Identity


class IdentityExistsError(Exception):
    """An identity with this name already exists."""


class IdentityRepository(Protocol):
    async def create(self, name: str, namespaces: list[str], token_sha256: str) -> Identity:
        """Create an identity; raises `IdentityExistsError` on a duplicate name."""
        ...

    async def get_by_token_hash(self, token_sha256: str) -> Identity | None:
        """The identity owning this token digest, or None when unknown or revoked."""
        ...

    async def list_identities(self) -> list[Identity]:
        """All identities, including revoked ones, oldest first."""
        ...

    async def revoke(self, name: str) -> Identity | None:
        """Revoke by name (idempotent); returns the identity, or None if unknown."""
        ...
