from __future__ import annotations

import pytest

from rootmem.identity.bind import UnsafeBindError, is_loopback, validate_http_bind


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
def test_loopback_hosts_are_always_allowed(host: str) -> None:
    assert is_loopback(host)
    validate_http_bind(host, allow_non_loopback=False)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_non_loopback_needs_explicit_opt_in(host: str) -> None:
    assert not is_loopback(host)
    with pytest.raises(UnsafeBindError):
        validate_http_bind(host, allow_non_loopback=False)
    validate_http_bind(host, allow_non_loopback=True)
