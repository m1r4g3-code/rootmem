"""The namespace export/import bundle format (ADR 0037). Pure.

A bundle is JSON Lines: line 1 is the manifest, every following line is one
record. The manifest carries the format version, the record counts and a
SHA-256 over the canonical record lines, so a corrupted or edited bundle is
refused on load instead of being half-imported.

Records reference each other by their *source* ids; the importer remaps them.
Embeddings, the audit log and soft-deleted rows are deliberately not part of
a bundle (see ADR 0037).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

BUNDLE_VERSION = 1

Kind = Literal[
    "memory",
    "entity",
    "relation",
    "memory_entity",
    "relation_provenance",
    "skill",
    "skill_provenance",
]

# Fixed order: referenced records come before the records that reference them,
# which is also the order an importer needs.
KIND_ORDER: tuple[Kind, ...] = (
    "memory",
    "entity",
    "relation",
    "memory_entity",
    "relation_provenance",
    "skill",
    "skill_provenance",
)


class BundleError(Exception):
    """The bundle is malformed, an unsupported version, or fails its digest."""


class BundleRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Kind
    data: dict[str, Any]


class BundleManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    source_namespace: str
    exported_at: datetime
    counts: dict[str, int]
    content_sha256: str


class Bundle(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest: BundleManifest
    records: list[BundleRecord]

    def of_kind(self, kind: Kind) -> list[dict[str, Any]]:
        return [record.data for record in self.records if record.kind == kind]


def _canonical(record: BundleRecord) -> str:
    return json.dumps(
        {"kind": record.kind, "data": record.data},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def content_digest(records: Iterable[BundleRecord]) -> str:
    joined = "\n".join(_canonical(record) for record in records)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _sort_key(record: BundleRecord) -> tuple[int, str]:
    return KIND_ORDER.index(record.kind), _canonical(record)


def build_bundle(
    source_namespace: str, records: Iterable[BundleRecord], exported_at: datetime
) -> Bundle:
    """Order records deterministically (so equal content gives an equal
    digest), then compute counts and the digest."""
    ordered = sorted(records, key=_sort_key)
    counts = {kind: 0 for kind in KIND_ORDER}
    for record in ordered:
        counts[record.kind] += 1
    manifest = BundleManifest(
        version=BUNDLE_VERSION,
        source_namespace=source_namespace,
        exported_at=exported_at,
        counts=counts,
        content_sha256=content_digest(ordered),
    )
    return Bundle(manifest=manifest, records=ordered)


def dump_jsonl(bundle: Bundle) -> str:
    lines = [bundle.manifest.model_dump_json()]
    lines.extend(_canonical(record) for record in bundle.records)
    return "\n".join(lines) + "\n"


def load_jsonl(text: str) -> Bundle:
    """Parse and VERIFY a bundle; raises `BundleError` on any problem."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise BundleError("empty bundle")
    try:
        manifest = BundleManifest.model_validate_json(lines[0])
    except ValueError as exc:
        raise BundleError(f"unreadable manifest: {exc}") from exc
    if manifest.version != BUNDLE_VERSION:
        raise BundleError(
            f"unsupported bundle version {manifest.version} (this build reads {BUNDLE_VERSION})"
        )
    try:
        records = [BundleRecord.model_validate_json(line) for line in lines[1:]]
    except ValueError as exc:
        raise BundleError(f"unreadable record: {exc}") from exc

    counts = {kind: 0 for kind in KIND_ORDER}
    for record in records:
        counts[record.kind] += 1
    if counts != manifest.counts:
        raise BundleError("record counts do not match the manifest")
    if content_digest(records) != manifest.content_sha256:
        raise BundleError("content digest mismatch: the bundle was altered or corrupted")
    return Bundle(manifest=manifest, records=records)
