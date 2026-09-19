"""Namespace authorization (ADR 0029). Pure."""

from __future__ import annotations

from rootmem.identity.models import ALL_NAMESPACES, Identity


class AuthorizationError(Exception):
    """The caller's identity does not own the requested namespace."""


def owns_namespace(identity: Identity, namespace: str) -> bool:
    if identity.is_revoked:
        return False
    return ALL_NAMESPACES in identity.namespaces or namespace in identity.namespaces


def authorize_namespace(identity: Identity, namespace: str) -> None:
    if not owns_namespace(identity, namespace):
        # Deliberately generic: do not reveal whether the namespace exists.
        raise AuthorizationError(f"identity {identity.name!r} may not access this namespace")
