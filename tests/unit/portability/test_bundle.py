from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rootmem.portability.bundle import (
    BUNDLE_VERSION,
    BundleError,
    BundleRecord,
    build_bundle,
    dump_jsonl,
    load_jsonl,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _records() -> list[BundleRecord]:
    return [
        BundleRecord(kind="skill", data={"id": "s1", "name": "fix-it"}),
        BundleRecord(kind="memory", data={"id": "m2", "content": "second"}),
        BundleRecord(kind="memory", data={"id": "m1", "content": "first"}),
        BundleRecord(kind="entity", data={"id": "e1", "name": "Alice"}),
        BundleRecord(kind="memory_entity", data={"memory_id": "m1", "entity_id": "e1"}),
    ]


def test_build_orders_records_by_kind_and_counts_them() -> None:
    bundle = build_bundle("ns-a", _records(), NOW)

    assert [r.kind for r in bundle.records] == [
        "memory",
        "memory",
        "entity",
        "memory_entity",
        "skill",
    ]
    assert bundle.manifest.counts["memory"] == 2
    assert bundle.manifest.counts["relation"] == 0
    assert bundle.manifest.version == BUNDLE_VERSION


def test_digest_is_independent_of_input_order() -> None:
    forward = build_bundle("ns", _records(), NOW)
    backward = build_bundle("ns", list(reversed(_records())), NOW)
    assert forward.manifest.content_sha256 == backward.manifest.content_sha256


def test_jsonl_round_trip_preserves_everything() -> None:
    bundle = build_bundle("ns-a", _records(), NOW)

    loaded = load_jsonl(dump_jsonl(bundle))

    assert loaded.records == bundle.records
    assert loaded.manifest == bundle.manifest
    assert loaded.of_kind("memory")[0]["content"] == "first"


def test_editing_a_record_is_detected() -> None:
    text = dump_jsonl(build_bundle("ns-a", _records(), NOW))
    with pytest.raises(BundleError, match="digest"):
        load_jsonl(text.replace("second", "tampered"))


def test_dropping_or_adding_a_record_is_detected() -> None:
    lines = dump_jsonl(build_bundle("ns-a", _records(), NOW)).splitlines()
    with pytest.raises(BundleError, match="counts"):
        load_jsonl("\n".join(lines[:-1]))
    extra = '{"data":{"id":"m9"},"kind":"memory"}'
    with pytest.raises(BundleError, match="counts"):
        load_jsonl("\n".join([*lines, extra]))


def test_malformed_and_unsupported_bundles_are_refused() -> None:
    with pytest.raises(BundleError, match="empty"):
        load_jsonl("")
    with pytest.raises(BundleError, match="manifest"):
        load_jsonl("not json")
    good = dump_jsonl(build_bundle("ns", _records(), NOW))
    with pytest.raises(BundleError, match="version"):
        load_jsonl(good.replace(f'"version":{BUNDLE_VERSION}', '"version":99', 1))
    with pytest.raises(BundleError, match="record"):
        load_jsonl(good + "garbage line\n")
