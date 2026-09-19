"""Export and import a namespace (ADR 0037).

    python -m rootmem.portability.cli export --namespace team --out team.jsonl
    python -m rootmem.portability.cli import --namespace team-copy --in team.jsonl

An operator action run against the database directly (like the identity CLI),
not an MCP tool. Import refuses a non-empty target namespace, verifies the
bundle's digest before writing anything, and appends one `import` entry to the
target namespace's audit chain carrying the bundle digest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rootmem.config import get_settings
from rootmem.portability.bundle import BundleError, dump_jsonl, load_jsonl
from rootmem.storage.audit_protocols import AuditLogRepository
from rootmem.storage.portability_protocols import NamespaceNotEmptyError, PortabilityRepository
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.portability_repository import PostgresPortabilityRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootmem.portability.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="write a namespace to a bundle file")
    export.add_argument("--namespace", required=True)
    export.add_argument("--out", type=Path, required=True)

    imp = sub.add_parser("import", help="load a bundle into an EMPTY namespace")
    imp.add_argument("--namespace", required=True, help="the target namespace")
    imp.add_argument("--in", dest="source", type=Path, required=True)
    imp.add_argument("--actor", default="operator-cli", help="recorded in the audit entry")
    return parser


async def run(
    args: argparse.Namespace, portability: PortabilityRepository, audit: AuditLogRepository
) -> int:
    if args.command == "export":
        bundle = await portability.export_namespace(args.namespace)
        args.out.write_text(dump_jsonl(bundle), encoding="utf-8")
        total = sum(bundle.manifest.counts.values())
        print(f"exported {total} records from {args.namespace!r} to {args.out}")
        print(f"content sha256: {bundle.manifest.content_sha256}")
        return 0

    try:
        bundle = load_jsonl(args.source.read_text(encoding="utf-8"))
    except (OSError, BundleError) as exc:
        print(f"error: cannot use bundle: {exc}", file=sys.stderr)
        return 1
    try:
        counts = await portability.import_bundle(args.namespace, bundle)
    except NamespaceNotEmptyError:
        print(
            f"error: namespace {args.namespace!r} is not empty; import needs an empty namespace",
            file=sys.stderr,
        )
        return 1
    await audit.append(
        args.namespace,
        args.actor,
        "import",
        "namespace",
        args.namespace,
        {
            "bundle_sha256": bundle.manifest.content_sha256,
            "source_namespace": bundle.manifest.source_namespace,
            "counts": counts,
        },
    )
    print(f"imported {sum(counts.values())} records into {args.namespace!r}")
    return 0


async def _main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    pool = await create_pool(get_settings())
    try:
        return await run(
            args, PostgresPortabilityRepository(pool), PostgresAuditLogRepository(pool)
        )
    finally:
        await pool.close()


def main() -> None:
    sys.exit(asyncio.run(_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
