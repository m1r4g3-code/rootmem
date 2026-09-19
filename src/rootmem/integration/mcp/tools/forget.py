"""`forget` — soft-delete a memory. Idempotent: repeated calls on an
already-deleted record return its existing deletion timestamp rather than
erroring. Never issues a hard delete (see ADR 0004)."""

from __future__ import annotations

from rootmem.integration.mcp.schemas import ForgetParams, ForgetResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.protocols import MemoryRepository


@log_operation("forget")
async def forget(repository: MemoryRepository, params: ForgetParams) -> ForgetResult:
    record = await repository.soft_delete(params.id, params.reason)
    assert record.deleted_at is not None
    return ForgetResult(id=record.id, deleted_at=record.deleted_at, namespace=record.namespace)
