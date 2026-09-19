"""REST facade over the tools (ADR 0036).

`GET /v1/tools` lists them, `POST /v1/tools/{name}` runs one with a JSON
object body. The facade authenticates the Bearer header with the same
verifier as the HTTP transport, sets the SDK's auth context, and calls the
server's own tool-call path -- so scopes, namespace authorization, rate
limits and audit are the MCP ones by construction, never a second copy.

Errors map from `ApiToolError.status_code` (401/403/404/429); any other
`ToolError` is a client error (422); an unexpected failure is a generic 500
that never echoes internals.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from rootmem.integration.errors import NOT_FOUND, UNAUTHENTICATED, UNPROCESSABLE, ApiToolError
from rootmem.integration.routes import add_route
from rootmem.logging import get_logger


def _error(status: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=headers)


async def _authenticate(request: Request, verifier: TokenVerifier) -> AccessToken | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return await verifier.verify_token(token.strip())


def mount_rest(server: MCPServer, verifier: TokenVerifier) -> None:
    async def list_tools(request: Request) -> Response:
        if await _authenticate(request, verifier) is None:
            return _error(
                UNAUTHENTICATED, "authentication required", {"WWW-Authenticate": "Bearer"}
            )
        tools = await server.list_tools()
        return JSONResponse(
            [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
        )

    async def call_tool(request: Request) -> Response:
        access = await _authenticate(request, verifier)
        if access is None:
            return _error(
                UNAUTHENTICATED, "authentication required", {"WWW-Authenticate": "Bearer"}
            )

        name = str(request.path_params["name"])
        if name not in {t.name for t in await server.list_tools()}:
            return _error(NOT_FOUND, f"unknown tool {name!r}")

        raw = await request.body()
        try:
            arguments: Any = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return _error(UNPROCESSABLE, "request body must be valid JSON")
        if not isinstance(arguments, dict):
            return _error(UNPROCESSABLE, "request body must be a JSON object")

        reset = auth_context_var.set(AuthenticatedUser(access))
        try:
            result = await server.call_tool(name, arguments)
        except UnexpectedToolError:
            get_logger().exception("REST tool call %s failed unexpectedly", name)
            return _error(500, "internal error")
        except ToolError as exc:
            # The SDK re-wraps every ToolError ("Error executing tool ...") and
            # keeps the original as __cause__; the typed status lives there.
            cause = exc.__cause__ if exc.__cause__ is not None else exc
            if isinstance(cause, ApiToolError):
                return _error(cause.status_code, str(cause))
            return _error(UNPROCESSABLE, str(exc))
        finally:
            auth_context_var.reset(reset)

        structured = getattr(result, "structured_content", None)
        return JSONResponse({"result": structured})

    add_route(server, "/v1/tools", ["GET"], list_tools)
    add_route(server, "/v1/tools/{name}", ["POST"], call_tool)
