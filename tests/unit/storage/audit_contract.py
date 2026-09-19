"""Shared behavioral contract for every `AuditLogRepository` implementation.

Base class, not a test file (no `test_` prefix). Subclasses provide an async
`repository` fixture and a `tamper` hook that rewrites one stored entry's
payload WITHOUT re-hashing, simulating direct storage tampering.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from rootmem.audit.chain import GENESIS_HASH, verify_chain
from rootmem.storage.audit_protocols import AuditLogRepository


class AuditLogRepositoryContract:
    @pytest.fixture
    def repository(self) -> AuditLogRepository:  # pragma: no cover - overridden
        raise NotImplementedError

    async def tamper(
        self, repository: AuditLogRepository, namespace: str, seq: int, payload: dict[str, Any]
    ) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def _ns() -> str:
        return f"audit-{uuid.uuid4().hex[:10]}"

    async def test_empty_namespace_has_no_entries_and_verifies(
        self, repository: AuditLogRepository
    ) -> None:
        entries = await repository.list_entries(self._ns())
        assert entries == []
        assert verify_chain(entries).valid is True

    async def test_first_entry_links_to_genesis_with_seq_one(
        self, repository: AuditLogRepository
    ) -> None:
        ns = self._ns()
        entry = await repository.append(ns, "tester", "remember", "memory", "m1", {"a": 1})
        assert entry.seq == 1
        assert entry.prev_hash == GENESIS_HASH

    async def test_entries_chain_and_verify(self, repository: AuditLogRepository) -> None:
        ns = self._ns()
        for i in range(4):
            await repository.append(ns, "tester", "update", "memory", f"m{i}", {"i": i})
        entries = await repository.list_entries(ns)
        assert [e.seq for e in entries] == [1, 2, 3, 4]
        assert entries[1].prev_hash == entries[0].row_hash
        assert verify_chain(entries).valid is True

    async def test_namespaces_have_independent_chains(self, repository: AuditLogRepository) -> None:
        a, b = self._ns(), self._ns()
        await repository.append(a, "t", "remember", "memory", "1", {})
        await repository.append(a, "t", "remember", "memory", "2", {})
        first_b = await repository.append(b, "t", "remember", "memory", "1", {})
        assert first_b.seq == 1
        assert first_b.prev_hash == GENESIS_HASH

    async def test_payload_round_trips(self, repository: AuditLogRepository) -> None:
        ns = self._ns()
        payload = {"nested": {"x": [1, 2, 3]}, "s": "text", "f": 0.5, "n": None}
        await repository.append(ns, "t", "remember", "memory", None, payload)
        (entry,) = await repository.list_entries(ns)
        assert entry.payload == payload
        assert entry.target_id is None
        assert verify_chain([entry]).valid is True

    async def test_tampering_is_detected_at_the_altered_row(
        self, repository: AuditLogRepository
    ) -> None:
        ns = self._ns()
        for i in range(5):
            await repository.append(ns, "t", "remember", "memory", f"m{i}", {"i": i})
        await self.tamper(repository, ns, 3, {"i": "forged"})
        result = verify_chain(await repository.list_entries(ns))
        assert result.valid is False
        assert result.first_broken_seq == 3

    async def test_concurrent_appends_never_fork_the_chain(
        self, repository: AuditLogRepository
    ) -> None:
        import asyncio

        ns = self._ns()
        await asyncio.gather(
            *(repository.append(ns, "t", "remember", "memory", f"m{i}", {"i": i}) for i in range(8))
        )
        entries = await repository.list_entries(ns)
        assert [e.seq for e in entries] == list(range(1, 9))
        assert verify_chain(entries).valid is True
