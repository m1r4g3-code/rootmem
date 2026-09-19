"""Manage agent identities (ADR 0027).

    python -m rootmem.identity.cli create --name alice --namespace ns-a --namespace ns-b
    python -m rootmem.identity.cli list
    python -m rootmem.identity.cli revoke --name alice

`create` prints the bearer token exactly once; only its SHA-256 digest is
stored, so a lost token cannot be recovered, only replaced by a new identity.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rootmem.config import get_settings
from rootmem.identity.models import ALL_NAMESPACES
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.storage.identity_protocols import IdentityExistsError, IdentityRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootmem.identity.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create an identity and print its token once")
    create.add_argument("--name", required=True)
    create.add_argument(
        "--namespace",
        action="append",
        required=True,
        dest="namespaces",
        help="a namespace this identity owns (repeatable)",
    )

    sub.add_parser("list", help="list identities (never shows tokens)")

    revoke = sub.add_parser(
        "revoke", help="revoke an identity; its token stops working immediately"
    )
    revoke.add_argument("--name", required=True)
    return parser


async def run(args: argparse.Namespace, identities: IdentityRepository) -> int:
    if args.command == "create":
        if ALL_NAMESPACES in args.namespaces:
            print(f"error: {ALL_NAMESPACES!r} is reserved for the local identity", file=sys.stderr)
            return 2
        token = generate_token()
        try:
            identity = await identities.create(args.name, args.namespaces, hash_token(token))
        except IdentityExistsError:
            print(f"error: an identity named {args.name!r} already exists", file=sys.stderr)
            return 1
        print(f"created identity {identity.name!r} owning {', '.join(identity.namespaces)}")
        print("token (shown once, store it now):")
        print(token)
        return 0

    if args.command == "list":
        for identity in await identities.list_identities():
            state = "revoked" if identity.is_revoked else "active"
            print(f"{identity.name}\t{state}\t{','.join(identity.namespaces)}")
        return 0

    revoked = await identities.revoke(args.name)
    if revoked is None:
        print(f"error: no identity named {args.name!r}", file=sys.stderr)
        return 1
    print(f"revoked {revoked.name!r}")
    return 0


async def _main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    pool = await create_pool(get_settings())
    try:
        return await run(args, PostgresIdentityRepository(pool))
    finally:
        await pool.close()


def main() -> None:
    sys.exit(asyncio.run(_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
