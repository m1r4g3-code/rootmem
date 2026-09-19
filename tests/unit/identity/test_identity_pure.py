from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rootmem.identity.authz import AuthorizationError, authorize_namespace, owns_namespace
from rootmem.identity.models import ALL_NAMESPACES, Identity, local_identity
from rootmem.identity.tokens import TOKEN_PREFIX, generate_token, hash_token

NOW = datetime(2026, 9, 19, tzinfo=UTC)


def _identity(namespaces: list[str], revoked: bool = False) -> Identity:
    return Identity(
        id="1",
        name="agent-a",
        namespaces=namespaces,
        created_at=NOW,
        revoked_at=NOW if revoked else None,
    )


def test_owner_may_access_its_namespace_only() -> None:
    identity = _identity(["ns-a"])
    authorize_namespace(identity, "ns-a")
    with pytest.raises(AuthorizationError):
        authorize_namespace(identity, "ns-b")


def test_error_message_does_not_name_the_namespace() -> None:
    with pytest.raises(AuthorizationError) as excinfo:
        authorize_namespace(_identity(["ns-a"]), "secret-ns")
    assert "secret-ns" not in str(excinfo.value)


def test_revoked_identity_owns_nothing() -> None:
    assert owns_namespace(_identity(["ns-a"], revoked=True), "ns-a") is False


def test_local_identity_owns_every_namespace() -> None:
    local = local_identity("rootmem-mcp", NOW)
    assert ALL_NAMESPACES in local.namespaces
    assert owns_namespace(local, "anything")


def test_tokens_are_unique_prefixed_and_hash_is_stable() -> None:
    first, second = generate_token(), generate_token()
    assert first != second
    assert first.startswith(TOKEN_PREFIX)
    assert hash_token(first) == hash_token(first)
    assert hash_token(first) != hash_token(second)
    assert len(hash_token(first)) == 64
    assert first not in hash_token(first)
