from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_consolidation_repository import (
    InMemoryConsolidationRepository,
)
from tests.unit.storage.consolidation_contract import ConsolidationRepositoryContract


class TestInMemoryConsolidationRepository(ConsolidationRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryConsolidationRepository:
        return InMemoryConsolidationRepository()
