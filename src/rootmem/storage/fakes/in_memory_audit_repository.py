"""Dict/list-backed `AuditLogRepository` for unit tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from rootmem.audit.chain import GENESIS_HASH, AuditEntry, compute_hash


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self._chains: dict[str, list[AuditEntry]] = {}
        self._lock = asyncio.Lock()

    async def append(
        self,
        namespace: str,
        actor: str,
        action: str,
        target_type: str,
        target_id: str | None,
        payload: dict[str, Any],
        created_at: datetime | None = None,
    ) -> AuditEntry:
        async with self._lock:
            chain = self._chains.setdefault(namespace, [])
            prev_hash = chain[-1].row_hash if chain else GENESIS_HASH
            seq = len(chain) + 1
            stamp = created_at if created_at is not None else datetime.now(UTC)
            entry = AuditEntry(
                namespace=namespace,
                seq=seq,
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                payload=payload,
                created_at=stamp,
                prev_hash=prev_hash,
                row_hash=compute_hash(
                    prev_hash, namespace, seq, actor, action, target_type, target_id, payload, stamp
                ),
            )
            chain.append(entry)
            return entry

    async def list_entries(self, namespace: str) -> list[AuditEntry]:
        return list(self._chains.get(namespace, []))

    def tamper_for_test(self, namespace: str, index: int, payload: dict[str, Any]) -> None:
        """Test-only: rewrite one stored entry's payload without re-hashing,
        simulating direct storage tampering."""
        chain = self._chains[namespace]
        chain[index] = chain[index].model_copy(update={"payload": payload})
