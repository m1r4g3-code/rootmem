from __future__ import annotations

import pytest

from rootmem.identity.cli import build_parser, run
from rootmem.identity.tokens import hash_token
from rootmem.storage.fakes.in_memory_identity_repository import InMemoryIdentityRepository


async def test_create_prints_token_once_and_stores_only_its_digest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = InMemoryIdentityRepository()
    code = await run(
        build_parser().parse_args(["create", "--name", "alice", "--namespace", "ns-a"]), repo
    )

    out = capsys.readouterr().out
    token = out.strip().splitlines()[-1]
    assert code == 0 and token.startswith("rmk_")
    found = await repo.get_by_token_hash(hash_token(token))
    assert found is not None and found.name == "alice"

    await run(build_parser().parse_args(["list"]), repo)
    assert token not in capsys.readouterr().out


async def test_duplicate_name_and_wildcard_namespace_are_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = InMemoryIdentityRepository()
    args = ["create", "--name", "alice", "--namespace", "ns-a"]
    assert await run(build_parser().parse_args(args), repo) == 0
    assert await run(build_parser().parse_args(args), repo) == 1
    star = ["create", "--name", "root", "--namespace", "*"]
    assert await run(build_parser().parse_args(star), repo) == 2
    assert "reserved" in capsys.readouterr().err


async def test_revoke_then_token_stops_working(capsys: pytest.CaptureFixture[str]) -> None:
    repo = InMemoryIdentityRepository()
    await run(build_parser().parse_args(["create", "--name", "alice", "--namespace", "n"]), repo)
    token = capsys.readouterr().out.strip().splitlines()[-1]

    assert await run(build_parser().parse_args(["revoke", "--name", "alice"]), repo) == 0
    assert await repo.get_by_token_hash(hash_token(token)) is None
    assert await run(build_parser().parse_args(["revoke", "--name", "nobody"]), repo) == 1
