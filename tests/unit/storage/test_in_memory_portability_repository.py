from __future__ import annotations

import pytest

from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_portability_repository import InMemoryPortabilityRepository
from rootmem.storage.fakes.in_memory_procedural_repository import (
    InMemoryProceduralMemoryRepository,
)
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from tests.unit.storage.portability_contract import PortabilityEnv, PortabilityRepositoryContract


class TestInMemoryPortabilityRepository(PortabilityRepositoryContract):
    @pytest.fixture
    def env(self) -> PortabilityEnv:
        memories = InMemoryMemoryRepository()
        graph = InMemoryGraphRepository()
        skills = InMemoryProceduralMemoryRepository()
        return PortabilityEnv(
            portability=InMemoryPortabilityRepository(memories, graph, skills),
            memories=memories,
            graph=graph,
            skills=skills,
        )
