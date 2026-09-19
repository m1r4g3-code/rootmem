from __future__ import annotations

from typing import Any

import pytest

from rootmem.storage.audit_protocols import AuditLogRepository
from rootmem.storage.fakes.in_memory_audit_repository import InMemoryAuditLogRepository
from tests.unit.storage.audit_contract import AuditLogRepositoryContract


class TestInMemoryAuditLogRepository(AuditLogRepositoryContract):
    @pytest.fixture
    def repository(self) -> InMemoryAuditLogRepository:
        return InMemoryAuditLogRepository()

    async def tamper(
        self, repository: AuditLogRepository, namespace: str, seq: int, payload: dict[str, Any]
    ) -> None:
        assert isinstance(repository, InMemoryAuditLogRepository)
        repository.tamper_for_test(namespace, seq - 1, payload)
