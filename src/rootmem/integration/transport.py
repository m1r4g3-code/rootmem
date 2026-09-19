"""HTTP transport security settings (ADR 0028, 0040). Pure.

The SDK enables Host/Origin (DNS-rebinding) protection automatically only for
loopback binds. A deployed server listens off-loopback behind a reverse proxy,
so protection stays off unless the operator names the hostnames it serves via
`ROOTMEM_HTTP_ALLOWED_HOSTS` (comma separated, e.g. `memory.example.com`).
"""

from __future__ import annotations

from mcp.server.transport_security import TransportSecuritySettings


def parse_hosts(csv: str) -> list[str]:
    return [host.strip().lower() for host in csv.split(",") if host.strip()]


def build_transport_security(allowed_hosts_csv: str) -> TransportSecuritySettings | None:
    """None (SDK default behavior) when no hosts are configured; otherwise
    protection is enabled for exactly those hosts, with or without a port."""
    hosts = parse_hosts(allowed_hosts_csv)
    if not hosts:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*hosts, *(f"{host}:*" for host in hosts)],
        allowed_origins=[
            *(f"https://{host}" for host in hosts),
            *(f"https://{host}:*" for host in hosts),
        ],
    )
