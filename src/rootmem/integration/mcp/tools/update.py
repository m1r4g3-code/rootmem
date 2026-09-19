"""`update` — apply a partial change to an existing, non-deleted memory.

Raises `rootmem.storage.protocols.NotFoundError` for a missing or
soft-deleted id; the MCP adapter (server.py) converts that into a
`ToolError` with the message intact, per ADR 0002.
"""

from __future__ import annotations

from rootmem.integration.mcp.schemas import UpdateParams, UpdateResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.models import MemoryUpdate
from rootmem.storage.protocols import MemoryRepository


@log_operation("update")
async def update(repository: MemoryRepository, params: UpdateParams) -> UpdateResult:
    changes = MemoryUpdate(
        content=params.content, confidence=params.confidence, metadata=params.metadata
    )
    record = await repository.update(params.id, changes)
    return UpdateResult(id=record.id, updated_at=record.updated_at, namespace=record.namespace)
