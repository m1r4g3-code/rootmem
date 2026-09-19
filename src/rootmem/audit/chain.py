"""Tamper-evident audit chain (ADR 0025, docs/math-spec/phase4-math-spec.md).

Pure: hashing and verification only, no I/O. Each entry commits to the
previous entry's hash, so altering, removing or reordering any earlier row
breaks every later link.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

GENESIS_HASH = "0" * 64


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    namespace: str
    seq: int
    actor: str
    action: str
    target_type: str
    target_id: str | None
    payload: dict[str, Any]
    created_at: datetime
    prev_hash: str
    row_hash: str


class ChainVerification(BaseModel):
    valid: bool
    entries_checked: int
    first_broken_seq: int | None = None
    reason: str | None = None


def compute_hash(
    prev_hash: str,
    namespace: str,
    seq: int,
    actor: str,
    action: str,
    target_type: str,
    target_id: str | None,
    payload: dict[str, Any],
    created_at: datetime,
) -> str:
    body = json.dumps(
        {
            "namespace": namespace,
            "seq": seq,
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
            "created_at": created_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def verify_chain(entries: Sequence[AuditEntry]) -> ChainVerification:
    """Verify entries of ONE namespace, ordered by `seq`, starting at the
    genesis. Reports the first entry whose link, sequence number or hash
    disagrees with a recomputation."""
    expected_prev = GENESIS_HASH
    for index, entry in enumerate(entries):
        if entry.seq != index + 1:
            return ChainVerification(
                valid=False,
                entries_checked=index,
                first_broken_seq=entry.seq,
                reason="sequence gap or reorder",
            )
        if entry.prev_hash != expected_prev:
            return ChainVerification(
                valid=False,
                entries_checked=index,
                first_broken_seq=entry.seq,
                reason="prev_hash does not match preceding row",
            )
        recomputed = compute_hash(
            entry.prev_hash,
            entry.namespace,
            entry.seq,
            entry.actor,
            entry.action,
            entry.target_type,
            entry.target_id,
            entry.payload,
            entry.created_at,
        )
        if recomputed != entry.row_hash:
            return ChainVerification(
                valid=False,
                entries_checked=index,
                first_broken_seq=entry.seq,
                reason="row_hash does not match row contents",
            )
        expected_prev = entry.row_hash
    return ChainVerification(valid=True, entries_checked=len(entries))
