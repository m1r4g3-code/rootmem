"""Dict-backed `IdentityRepository` for unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from rootmem.identity.models import Identity
from rootmem.storage.identity_protocols import IdentityExistsError


class InMemoryIdentityRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Identity] = {}
        self._digest_by_id: dict[str, str] = {}

    async def create(self, name: str, namespaces: list[str], token_sha256: str) -> Identity:
        if any(identity.name == name for identity in self._by_id.values()):
            raise IdentityExistsError(name)
        identity = Identity(
            id=str(uuid.uuid4()),
            name=name,
            namespaces=list(namespaces),
            created_at=datetime.now(UTC),
        )
        self._by_id[identity.id] = identity
        self._digest_by_id[identity.id] = token_sha256
        return identity

    async def get_by_token_hash(self, token_sha256: str) -> Identity | None:
        for identity_id, digest in self._digest_by_id.items():
            if digest == token_sha256:
                identity = self._by_id[identity_id]
                return None if identity.is_revoked else identity
        return None

    async def list_identities(self) -> list[Identity]:
        return sorted(self._by_id.values(), key=lambda i: i.created_at)

    async def revoke(self, name: str) -> Identity | None:
        for identity in self._by_id.values():
            if identity.name == name:
                if not identity.is_revoked:
                    identity = identity.model_copy(update={"revoked_at": datetime.now(UTC)})
                    self._by_id[identity.id] = identity
                return identity
        return None
