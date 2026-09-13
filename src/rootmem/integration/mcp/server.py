"""MCP server entry point — a thin adapter over `rootmem.integration.mcp.tools`
(see ADR 0002). This module is the only place that:

- flattens each tool's individual keyword parameters into the validated
  internal `*Params` models from `schemas.py`, translating a validation
  failure into `ToolError` so its message reaches the client instead of
  being swallowed as an opaque crash (see the mcp 2.x `Tool.run` behavior:
  only `ToolError` preserves its message on the wire — everything else
  becomes a generic "Error executing tool <name>"), and
- translates `NotFoundError` into `ToolError` for the same reason.

`StorageError` (and anything else unanticipated) is deliberately left to
propagate uncaught: mcp's own `Tool.run` logs the full traceback server-side
via `logger.exception(...)` and returns a generic error to the client —
exactly the "no raw stack trace, no silent no-op" hardening behavior the
Phase 0 plan calls for, without this module reimplementing it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from rootmem.config import get_settings
from rootmem.integration.mcp.schemas import (
    ForgetParams,
    ForgetResult,
    RecallParams,
    RecallResult,
    RememberParams,
    RememberResult,
    SearchParams,
    SearchResponse,
    UpdateParams,
    UpdateResult,
)
from rootmem.integration.mcp.tools.forget import forget as forget_impl
from rootmem.integration.mcp.tools.recall import recall as recall_impl
from rootmem.integration.mcp.tools.remember import remember as remember_impl
from rootmem.integration.mcp.tools.search import search as search_impl
from rootmem.integration.mcp.tools.update import update as update_impl
from rootmem.logging import configure_logging, get_logger
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.repository import PostgresMemoryRepository
from rootmem.storage.protocols import MemoryRepository, NotFoundError


def _validated[ModelT: BaseModel](model: type[ModelT], **kwargs: Any) -> ModelT:
    try:
        return model(**kwargs)
    except PydanticValidationError as exc:
        messages = "; ".join(str(e["msg"]) for e in exc.errors())
        raise ToolError(messages) from exc


def build_server(repository: MemoryRepository) -> MCPServer:
    server = MCPServer(name="rootmem")

    @server.tool()
    async def remember(
        content: str,
        source: str,
        namespace: str = "default",
        key: str | None = None,
        source_session_id: str | None = None,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RememberResult:
        """Persist a new memory. If `idempotency_key` collides with an existing,
        non-deleted memory in the same namespace, returns that memory instead
        of creating a duplicate."""
        params = _validated(
            RememberParams,
            content=content,
            source=source,
            namespace=namespace,
            key=key,
            source_session_id=source_session_id,
            confidence=confidence,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )
        return await remember_impl(repository, params)

    @server.tool()
    async def recall(
        id: str | None = None,
        key: str | None = None,
        namespace: str = "default",
    ) -> RecallResult:
        """Fetch a single memory by exactly one of `id` or `key`. Returns
        `found=false` (not an error) if no matching, non-deleted memory exists."""
        params = _validated(RecallParams, id=id, key=key, namespace=namespace)
        return await recall_impl(repository, params)

    @server.tool()
    async def update(
        id: str,
        content: str | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UpdateResult:
        """Apply a partial update to an existing, non-deleted memory. At least
        one of `content`, `confidence`, or `metadata` is required."""
        params = _validated(
            UpdateParams, id=id, content=content, confidence=confidence, metadata=metadata
        )
        try:
            return await update_impl(repository, params)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def forget(id: str, reason: str | None = None) -> ForgetResult:
        """Soft-delete a memory. Idempotent: forgetting an already-deleted
        memory succeeds and returns its existing deletion timestamp."""
        params = _validated(ForgetParams, id=id, reason=reason)
        try:
            return await forget_impl(repository, params)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def search(
        query: str,
        namespace: str = "default",
        limit: int = 10,
        source: str | None = None,
    ) -> SearchResponse:
        """Ranked full-text search over non-deleted memories in a namespace."""
        params = _validated(
            SearchParams, query=query, namespace=namespace, limit=limit, source=source
        )
        return await search_impl(repository, params)

    return server


async def main_async() -> None:
    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    pool = await create_pool(settings)
    try:
        repository = PostgresMemoryRepository(pool)
        server = build_server(repository)
        logger.info("rootmem MCP server starting (stdio transport)")
        await server.run_stdio_async()
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
