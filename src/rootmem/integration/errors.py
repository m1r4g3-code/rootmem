"""Tool errors that carry an HTTP status (ADR 0036).

`ApiToolError` is still a `ToolError`, so MCP clients see exactly what they
saw before; the REST facade reads `status_code` instead of parsing messages.
"""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError


class ApiToolError(ToolError):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


UNAUTHENTICATED = 401
FORBIDDEN = 403
NOT_FOUND = 404
UNPROCESSABLE = 422
TOO_MANY_REQUESTS = 429
