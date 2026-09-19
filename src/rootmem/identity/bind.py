"""HTTP bind-address policy (ADR 0028, NFR4). Pure."""

from __future__ import annotations

import ipaddress

_LOOPBACK_NAMES = {"localhost"}


class UnsafeBindError(Exception):
    """A non-loopback bind was requested without explicit opt-in."""


def is_loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_http_bind(host: str, allow_non_loopback: bool) -> None:
    """Refuse to listen beyond loopback unless the operator opted in."""
    if not is_loopback(host) and not allow_non_loopback:
        raise UnsafeBindError(
            f"refusing to bind {host!r}: only loopback is allowed unless "
            "ROOTMEM_HTTP_ALLOW_NON_LOOPBACK is set (terminate TLS in a reverse proxy)"
        )
