"""`recall` — fetch a single memory by id or key. Not-found is a normal
negative result (`found=False`), not an error.

A successful recall reinforces the memory (access tracking, ADR 0023).
Tracking is best-effort: a failure there never fails the read.
"""

from __future__ import annotations

from datetime import UTC, datetime

from rootmem.integration.mcp.schemas import MemoryView, RecallParams, RecallResult
from rootmem.logging import get_logger
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

    try:
        await repository.record_access([record.id], datetime.now(UTC))
    except Exception:  # noqa: BLE001 - tracking is best-effort by design
        get_logger().warning("record_access failed; recall result unaffected", exc_info=True)
    return RecallResult(found=True, record=MemoryView.from_record(record))
