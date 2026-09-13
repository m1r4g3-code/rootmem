"""`remember` — persist a new memory (or return the existing one on idempotency-key collision).

This module holds pure business logic only: no MCP-specific types. It is
exercised directly in unit tests against `InMemoryMemoryRepository`, and
wrapped by an MCP-visible tool function in `integration.mcp.server`, which
is the only place that translates domain exceptions into MCP-specific
error types (see ADR 0002 — server.py is a thin adapter).
"""

from __future__ import annotations

from rootmem.integration.mcp.schemas import RememberParams, RememberResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.models import NewMemory
from rootmem.storage.protocols import MemoryRepository


@log_operation("remember")
async def remember(repository: MemoryRepository, params: RememberParams) -> RememberResult:
    record = await repository.create(
        NewMemory(
            namespace=params.namespace,
            key=params.key,
            idempotency_key=params.idempotency_key,
            content=params.content,
            source=params.source,
            source_session_id=params.source_session_id,
            confidence=params.confidence,
            metadata=params.metadata,
        )
    )
    return RememberResult(id=record.id, created_at=record.created_at)
