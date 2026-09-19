"""A typed wrapper around the SDK's untyped `MCPServer.custom_route`.

The SDK decorator has no return annotation, which `mypy --strict` rejects at
every use. Wrapping it once, here, keeps the rest of the codebase honestly
typed without scattering suppressions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import Response

RouteHandler = Callable[[Request], Awaitable[Response]]


def add_route(
    server: MCPServer, path: str, methods: list[str], handler: RouteHandler
) -> RouteHandler:
    """Register `handler` at `path`. These routes bypass the SDK's bearer
    middleware, so a handler that needs authentication must do it itself."""
    register = cast(
        "Callable[[str, list[str]], Callable[[RouteHandler], RouteHandler]]",
        server.custom_route,
    )
    return register(path, methods)(handler)
