# ADR 0002: MCP Python SDK (FastMCP) over stdio transport

**Status:** Accepted
**Date:** 2026-09-13

## Context

Phase 0 must expose 5 tools (`remember`, `recall`, `update`, `forget`, `search`) to local MCP clients — specifically Claude Code and Cursor, per the manual exit-criterion validation. The official MCP Python SDK offers both a low-level `Server` class (manual protocol handling) and a high-level `mcp.server.fastmcp.FastMCP` decorator API. Transport options include stdio (local subprocess) and SSE/HTTP (network-addressable server).

## Decision

Use the official `mcp` PyPI package's high-level server class, registering the 5 tools as decorated functions. Serve over **stdio** transport only.

**Implementation note (discovered when actually running `uv add mcp`):** the latest `mcp` release at implementation time is `2.2.0`, which renamed `mcp.server.fastmcp.FastMCP` to `mcp.server.mcpserver.MCPServer` (importing the old path raises a `ModuleNotFoundError` with a migration pointer). The API is otherwise the same shape this ADR was written for — a `.tool()` decorator for registering functions and `.run(transport="stdio")` (stdio is the default) to serve. This is exactly the kind of version-specific detail this ADR originally flagged as "must be pinned by checking current PyPI availability, not guessed in advance" — the guess (`FastMCP`) turned out to be the pre-2.x name, confirmed and corrected against the real installed package rather than left wrong in the docs.

## Rationale

**High-level `MCPServer` vs. low-level `Server`:** 5 simple, independent tools with straightforward pydantic-validated I/O is exactly this API's design target — the low-level `Server` class exists for cases needing custom protocol-level behavior (streaming, custom capabilities negotiation) that Phase 0 does not need. Using the low-level API here would be unjustified complexity.

**stdio vs. SSE/HTTP:** Both Claude Code and Cursor launch local MCP servers as child processes communicating over stdio by default — this is exactly the mechanism the manual validation checklist needs (launch client → client spawns server subprocess → tool calls flow over stdio). SSE/HTTP transport would require standing up a web server, managing a port, and adding authentication for zero Phase 0 benefit (no remote client exists yet); that surface area belongs to Phase 6 (Ecosystem Integration), where a transparent-proxy mode and multi-client access are actual requirements.

## Alternatives considered

- **Low-level `Server` class.** Rejected: more boilerplate for no capability Phase 0 needs.
- **SSE/HTTP transport now**, anticipating Phase 6. Rejected: adds a web server, port management, and auth surface a full 6 phases early; YAGNI until there's a remote client.

## Consequences

- `src/rootmem/integration/mcp/server.py` is kept as a thin adapter that wires `tools/*.py` functions into the FastMCP app and starts stdio transport. Tool logic itself has no transport dependency, so adding an HTTP/SSE transport later (Phase 6) means adding a new entry point, not touching `tools/*.py`.
- The exact `mcp` package version must be pinned in `pyproject.toml`/`uv.lock` at implementation time by checking current PyPI availability — not guessed in advance of running `uv add mcp`.
