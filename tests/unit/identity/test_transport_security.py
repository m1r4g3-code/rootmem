from __future__ import annotations

from starlette.testclient import TestClient

from rootmem.integration.transport import build_transport_security, parse_hosts
from tests.unit.identity.test_server_authorization import _Rig


def test_no_hosts_means_sdk_default() -> None:
    assert build_transport_security("") is None
    assert build_transport_security(" , ,") is None


def test_hosts_are_normalized_and_allowed_with_and_without_port() -> None:
    assert parse_hosts(" Memory.Example.com , other.test ") == ["memory.example.com", "other.test"]
    security = build_transport_security("memory.example.com")
    assert security is not None and security.enable_dns_rebinding_protection
    assert "memory.example.com" in security.allowed_hosts
    assert "memory.example.com:*" in security.allowed_hosts
    assert "https://memory.example.com" in security.allowed_origins


async def test_a_foreign_host_header_is_rejected_when_hosts_are_configured() -> None:
    security = build_transport_security("memory.example.com")

    async def status_for(host: str) -> int:
        # The SDK's session manager runs once per server, so use a fresh one.
        rig = _Rig(authenticated=True)
        token = (await rig.issue("agent", ["ns"])).token
        app = rig.server.streamable_http_app(transport_security=security, host="0.0.0.0")
        with TestClient(app, base_url=f"http://{host}") as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                headers={
                    "Host": host,
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json, text/event-stream",
                },
            )
        return response.status_code

    assert await status_for("evil.test") == 421  # Invalid Host header
    assert await status_for("memory.example.com") not in (401, 421)  # past host validation
