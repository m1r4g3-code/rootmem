from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from tests.unit.storage.graph_contract import GraphRepositoryContract


class TestInMemoryGraphRepository(GraphRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryGraphRepository:
        return InMemoryGraphRepository(contradiction_confidence_floor=0.5)
