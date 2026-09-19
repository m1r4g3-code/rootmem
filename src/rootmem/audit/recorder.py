"""`AuditRecorder` -- the one place tool handlers append audit entries
(ADR 0025). A recorder built with no repository is a deliberate no-op (used
by unit tests and by callers that have not been given an audit store)."""

from __future__ import annotations

import hashlib
from typing import Any

from rootmem.storage.audit_protocols import AuditLogRepository


def content_sha256(text: str) -> str:
    """Audit payloads carry a digest of content, never the content itself."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AuditRecorder:
    def __init__(self, repository: AuditLogRepository | None, actor: str) -> None:
        self._repository = repository
        self._actor = actor

    @property
    def enabled(self) -> bool:
        return self._repository is not None

    async def record(
        self,
        namespace: str,
        action: str,
        target_type: str,
        target_id: str | None,
        payload: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> None:
        """Append one entry. Propagates `StorageError` on failure: an
        operation that cannot be audited must be reported, never silently
        left unaudited (NFR6)."""
        if self._repository is None:
            return
        await self._repository.append(
            namespace,
            actor if actor is not None else self._actor,
            action,
            target_type,
            target_id,
            payload or {},
        )
