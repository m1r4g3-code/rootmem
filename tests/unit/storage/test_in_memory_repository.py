from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from tests.unit.storage.contract import MemoryRepositoryContract


class TestInMemoryMemoryRepository(MemoryRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryMemoryRepository:
        return InMemoryMemoryRepository()
