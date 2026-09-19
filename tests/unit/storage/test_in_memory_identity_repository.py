from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_identity_repository import InMemoryIdentityRepository
from tests.unit.storage.identity_contract import IdentityRepositoryContract


class TestInMemoryIdentityRepository(IdentityRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryIdentityRepository:
        return InMemoryIdentityRepository()
