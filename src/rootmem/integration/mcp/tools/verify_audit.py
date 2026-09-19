"""`verify_audit` — recompute one namespace's audit hash chain and report
the first tampered or missing entry (ADR 0025)."""

from __future__ import annotations

from rootmem.audit.chain import verify_chain
from rootmem.integration.mcp.schemas import VerifyAuditParams, VerifyAuditResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.audit_protocols import AuditLogRepository


@log_operation("verify_audit")
async def verify_audit(
    audit_repository: AuditLogRepository | None, params: VerifyAuditParams
) -> VerifyAuditResult:
    if audit_repository is None:
        return VerifyAuditResult(valid=True, entries_checked=0, audit_enabled=False)
    result = verify_chain(await audit_repository.list_entries(params.namespace))
    return VerifyAuditResult(
        valid=result.valid,
        entries_checked=result.entries_checked,
        first_broken_seq=result.first_broken_seq,
        reason=result.reason,
    )
