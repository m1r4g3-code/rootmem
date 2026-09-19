"""The audit-log storage port: `AuditLogRepository` (ADR 0025).

A separate Protocol: an audit entry is its own aggregate, neither a memory,
a relation, nor a consolidation run. Append-only by construction -- there is
deliberately no update or delete method. `PostgresAuditLogRepository` and
`InMemoryAuditLogRepository` satisfy it and share a contract-test suite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from rootmem.audit.chain import AuditEntry


class AuditLogRepository(Protocol):
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
        """Append one entry to the namespace's chain. Assigns the next `seq`
        and links `prev_hash` to the previous row's hash atomically, so
        concurrent appends to one namespace never fork the chain."""
        ...

    async def list_entries(self, namespace: str) -> list[AuditEntry]:
        """All entries of one namespace's chain, ordered by `seq`."""
        ...
