"""Shared behavioral contract for every `IdentityRepository` implementation.

Base class, not a test file (no `test_` prefix). Names are unique per test
so Postgres runs never collide with rows from other tests.
"""

from __future__ import annotations

import uuid

import pytest

from rootmem.identity.tokens import generate_token, hash_token
from rootmem.storage.identity_protocols import IdentityExistsError, IdentityRepository


class IdentityRepositoryContract:
    @pytest.fixture
    def repository(self) -> IdentityRepository:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def _name() -> str:
        return f"agent-{uuid.uuid4().hex[:10]}"

    async def test_create_then_lookup_by_token_hash(self, repository: IdentityRepository) -> None:
        name = self._name()
        digest = hash_token(generate_token())

        created = await repository.create(name, ["ns-a", "ns-b"], digest)
        found = await repository.get_by_token_hash(digest)

        assert found is not None
        assert found.id == created.id
        assert found.name == name
        assert found.namespaces == ["ns-a", "ns-b"]
        assert found.is_revoked is False

    async def test_unknown_token_hash_is_none(self, repository: IdentityRepository) -> None:
        assert await repository.get_by_token_hash(hash_token(generate_token())) is None

    async def test_duplicate_name_is_rejected(self, repository: IdentityRepository) -> None:
        name = self._name()
        await repository.create(name, ["ns"], hash_token(generate_token()))

        with pytest.raises(IdentityExistsError):
            await repository.create(name, ["ns"], hash_token(generate_token()))

    async def test_revoked_identity_no_longer_authenticates(
        self, repository: IdentityRepository
    ) -> None:
        name = self._name()
        digest = hash_token(generate_token())
        await repository.create(name, ["ns"], digest)

        revoked = await repository.revoke(name)

        assert revoked is not None and revoked.is_revoked
        assert await repository.get_by_token_hash(digest) is None

    async def test_revoke_is_idempotent_and_unknown_is_none(
        self, repository: IdentityRepository
    ) -> None:
        name = self._name()
        await repository.create(name, ["ns"], hash_token(generate_token()))

        first = await repository.revoke(name)
        second = await repository.revoke(name)

        assert first is not None and second is not None
        assert first.revoked_at == second.revoked_at
        assert await repository.revoke(self._name()) is None

    async def test_list_includes_revoked_identities(self, repository: IdentityRepository) -> None:
        name = self._name()
        await repository.create(name, ["ns"], hash_token(generate_token()))
        await repository.revoke(name)

        listed = await repository.list_identities()

        assert any(i.name == name and i.is_revoked for i in listed)
