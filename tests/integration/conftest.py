"""Shared fixtures for tests that launch the real MCP server as a
subprocess over stdio (test_mcp_server_e2e.py and
test_phase1_exit_criterion.py) — extracted here so both share one
definition of the env-forwarding list and the Windows teardown workaround
rather than drifting apart."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator

import pytest_asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_ENV_VARS_TO_FORWARD = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_SSLMODE",
    "ROOTMEM_LOG_LEVEL",
    # Phase 1: the real server now constructs VoyageEmbeddingProvider and
    # AnthropicExtractionProvider at startup (ADR 0009), which fail fast
    # without these — the subprocess needs them forwarded too.
    "VOYAGE_API_KEY",
    "ANTHROPIC_API_KEY",
    # Phase 4: per-source trust map (JSON), set by the Phase 4 exit test.
    "TRUST_SOURCE_RELIABILITY",
)


@pytest_asyncio.fixture
async def mcp_session() -> AsyncIterator[ClientSession]:
    server_env = {name: os.environ[name] for name in _ENV_VARS_TO_FORWARD if name in os.environ}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "rootmem.integration.mcp.server"],
        env=server_env,
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client_session:
                await client_session.initialize()
                yield client_session
    except RuntimeError as exc:
        # Known Windows-specific anyio/mcp SDK teardown quirk: closing the
        # subprocess's stdio pipes can raise "Attempted to exit cancel scope
        # in a different task than it was entered in" from stdio_client's
        # own __aexit__, strictly during cleanup, after the test body (and
        # its assertions) have already completed successfully. Suppress
        # only this specific message so a real failure still surfaces.
        if "cancel scope" not in str(exc):
            raise
