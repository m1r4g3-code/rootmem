"""`recall` — fetch a single memory by id or key. Not-found is a normal
negative result (`found=False`), not an error."""

from __future__ import annotations

from rootmem.integration.mcp.schemas import MemoryView, RecallParams, RecallResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.protocols import MemoryRepository


@log_operation("recall")
async def recall(repository: MemoryRepository, params: RecallParams) -> RecallResult:
    if params.id is not None:
        record = await repository.get_by_id(params.namespace, params.id)
    else:
        assert params.key is not None  # enforced by RecallParams's model_validator
        record = await repository.get_by_key(params.namespace, params.key)

    if record is None:
        return RecallResult(found=False)
    return RecallResult(found=True, record=MemoryView.from_record(record))
