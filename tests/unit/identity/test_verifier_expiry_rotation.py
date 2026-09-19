from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootmem.identity.tokens import generate_token, hash_token
from rootmem.identity.verifier import RootmemTokenVerifier
from rootmem.storage.fakes.in_memory_identity_repository import InMemoryIdentityRepository

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


async def test_expired_token_is_rejected_and_unexpired_is_accepted() -> None:
    repo = InMemoryIdentityRepository()
    token = generate_token()
    await repo.create("alice", ["ns"], hash_token(token), expires_at=NOW + timedelta(hours=1))

    before = RootmemTokenVerifier(repo, clock=lambda: NOW)
    after = RootmemTokenVerifier(repo, clock=lambda: NOW + timedelta(hours=1, seconds=1))

    accepted = await before.verify_token(token)
    assert accepted is not None
    assert accepted.claims is not None and accepted.claims["scope"] == "readwrite"
    assert await after.verify_token(token) is None


async def test_token_without_expiry_never_expires() -> None:
    repo = InMemoryIdentityRepository()
    token = generate_token()
    await repo.create("alice", ["ns"], hash_token(token))
    far_future = RootmemTokenVerifier(repo, clock=lambda: NOW + timedelta(days=36500))
    assert await far_future.verify_token(token) is not None


async def test_rotation_kills_the_old_token_and_keeps_scope_claim() -> None:
    repo = InMemoryIdentityRepository()
    old, new = generate_token(), generate_token()
    await repo.create("alice", ["ns"], hash_token(old), scope="read")
    verifier = RootmemTokenVerifier(repo, clock=lambda: NOW)

    assert await verifier.verify_token(old) is not None
    await repo.rotate("alice", hash_token(new))

    assert await verifier.verify_token(old) is None
    rotated = await verifier.verify_token(new)
    assert rotated is not None
    assert rotated.claims is not None and rotated.claims["scope"] == "read"
