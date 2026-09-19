"""The Phase 5 exit criterion (docs/requirements/phase5-requirements.md),
proven against a real uvicorn server process in HTTP mode and real Postgres.

(a) no token, an unknown token and a revoked token are all rejected (401);
(b) identity A writes from client 1; a brand-new client 2 with the same token
    reads it, including after the server process is restarted (continuity);
(c) identity B is denied every namespaced tool on A's namespace and nothing
    changes;
(d) the audit chain for A's namespace names A as actor and verifies;
(f) the integration database is a `_test` one (the guard fixture enforces it).

(e), stdio unchanged, is the rest of the suite. `remember` embeds via the real
Voyage API (it degrades gracefully if that fails), hence integration_external.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import httpx2
import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from rootmem.config import get_settings
from rootmem.identity.tokens import generate_token, hash_token
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.identity_repository import PostgresIdentityRepository

pytestmark = pytest.mark.integration_external

_ENV_TO_FORWARD = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_SSLMODE",
    "ROOTMEM_LOG_LEVEL",
    "VOYAGE_API_KEY",
    "ANTHROPIC_API_KEY",
    "SYSTEMROOT",
    "PATH",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _HttpServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self.url = f"http://127.0.0.1:{port}/mcp"
        self._proc: subprocess.Popen[bytes] | None = None

    async def start(self) -> None:
        env = {k: os.environ[k] for k in _ENV_TO_FORWARD if k in os.environ}
        env["POSTGRES_DB"] = get_settings().postgres_db  # the _test database
        env["ROOTMEM_TRANSPORT"] = "http"
        env["ROOTMEM_HTTP_PORT"] = str(self.port)
        self._proc = subprocess.Popen(  # noqa: ASYNC220 - one-off test server launch
            [sys.executable, "-m", "rootmem.integration.mcp.server"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        async with httpx2.AsyncClient() as client:
            for _ in range(120):
                if self._proc.poll() is not None:
                    raise RuntimeError("HTTP server exited during startup")
                try:
                    await client.post(self.url, json={})
                    return
                except httpx2.TransportError:
                    await asyncio.sleep(0.5)
        raise RuntimeError("HTTP server did not start listening")

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None


@asynccontextmanager
async def _client(url: str, token: str) -> AsyncIterator[ClientSession]:
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60)
    async with http, streamable_http_client(url, http_client=http) as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call(session: ClientSession, tool: str, **args: Any) -> types.CallToolResult:
    return await session.call_tool(tool, args)


def _ok(result: types.CallToolResult) -> dict[str, Any]:
    assert result.is_error is not True, f"tool call failed: {result.content}"
    assert result.structured_content is not None
    return cast("dict[str, Any]", result.structured_content)


@pytest.mark.asyncio
async def test_remote_identity_continuity_authorization_and_audit() -> None:
    suffix = uuid.uuid4().hex[:8]
    ns_a, ns_b = f"phase5-a-{suffix}", f"phase5-b-{suffix}"
    name_a, name_b, name_c = f"alice-{suffix}", f"bob-{suffix}", f"carol-{suffix}"
    token_a, token_b, token_c = generate_token(), generate_token(), generate_token()

    pool = await create_pool(get_settings())
    server = _HttpServer(_free_port())
    try:
        identities = PostgresIdentityRepository(pool)
        await identities.create(name_a, [ns_a], hash_token(token_a))
        await identities.create(name_b, [ns_b], hash_token(token_b))
        await identities.create(name_c, [ns_a], hash_token(token_c))
        await identities.revoke(name_c)

        await server.start()

        # --- (a) authentication is mandatory ---
        async with httpx2.AsyncClient() as raw:
            for headers in (
                {},
                {"Authorization": "Bearer rmk_not-a-real-token"},
                {"Authorization": f"Bearer {token_c}"},  # revoked
            ):
                response = await raw.post(server.url, json={}, headers=headers)
                assert response.status_code == 401, headers

        # --- (b) A writes from client 1 ---
        async with _client(server.url, token_a) as client1:
            remembered = _ok(
                await _call(
                    client1,
                    "remember",
                    content="the deploy key rotates every friday",
                    source="phase5-test",
                    namespace=ns_a,
                )
            )
        memory_id = remembered["id"]

        # ... and, after a full server restart, a brand-new client 2 reads it.
        server.stop()
        await server.start()
        async with _client(server.url, token_a) as client2:
            recalled = _ok(await _call(client2, "recall", id=memory_id, namespace=ns_a))
            assert recalled["found"] is True
            assert recalled["record"]["content"] == "the deploy key rotates every friday"
            found = _ok(
                await _call(
                    client2, "search", query="deploy key friday", namespace=ns_a, mode="text"
                )
            )
            assert memory_id in [item["id"] for item in found["results"]]

        # --- (c) B is denied everywhere on A's namespace; nothing changes ---
        async with _client(server.url, token_b) as client_b:
            for tool, args in (
                ("recall", {"id": memory_id, "namespace": ns_a}),
                ("search", {"query": "deploy", "namespace": ns_a}),
                ("remember", {"content": "x", "source": "t", "namespace": ns_a}),
                ("verify_audit", {"namespace": ns_a}),
                ("update", {"id": memory_id, "content": "hijacked"}),
                ("forget", {"id": memory_id}),
            ):
                result = await _call(client_b, tool, **args)
                assert result.is_error is True, tool
            # B's own namespace still works.
            own = await _call(
                client_b, "remember", content="bob fact", source="phase5-test", namespace=ns_b
            )
            assert own.is_error is not True

        async with _client(server.url, token_a) as client_a:
            unchanged = _ok(await _call(client_a, "recall", id=memory_id, namespace=ns_a))
            assert unchanged["record"]["content"] == "the deploy key rotates every friday"

            # --- (d) the audit chain names A and verifies ---
            verified = _ok(await _call(client_a, "verify_audit", namespace=ns_a))
            assert verified["valid"] is True
            assert verified["entries_checked"] == 1  # only A's remember; B's denials wrote nothing

        entries = await PostgresAuditLogRepository(pool).list_entries(ns_a)
        assert [entry.actor for entry in entries] == [name_a]
    finally:
        server.stop()
        await pool.close()
