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
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from rootmem.config import Settings, get_settings
from rootmem.embedding.protocols import EmbeddingProvider
from rootmem.extraction.models import ExtractionContext, ExtractionResult
from rootmem.extraction.protocols import ExtractionProvider

# `voyageai`/`anthropic` are deliberately NOT imported at module level: a real
# run on this machine measured `import voyageai` alone taking ~12s (the
# first import in-process to pull in the httpx/httpcore/certifi chain pays
# some OS-level one-time cost here — see `_LazyEmbeddingProvider` below).
# Importing them at module level would pay that cost before the MCP server
# even starts listening for the handshake, which is the bug being fixed.
if TYPE_CHECKING:
    from rootmem.embedding.voyage import VoyageEmbeddingProvider
    from rootmem.extraction.anthropic_provider import AnthropicExtractionProvider
from rootmem.integration.mcp.schemas import (
    ForgetParams,
    ForgetResult,
    IngestSessionParams,
    IngestSessionResult,
    RecallParams,
    RecallResult,
    RelatedParams,
    RelatedResult,
    RememberParams,
    RememberResult,
    SearchParams,
    SearchResponse,
    UpdateParams,
    UpdateResult,
)
from rootmem.integration.mcp.tools.forget import forget as forget_impl
from rootmem.integration.mcp.tools.ingest_session import ingest_session as ingest_session_impl
from rootmem.integration.mcp.tools.recall import recall as recall_impl
from rootmem.integration.mcp.tools.related import related as related_impl
from rootmem.integration.mcp.tools.remember import remember as remember_impl
from rootmem.integration.mcp.tools.search import search as search_impl
from rootmem.integration.mcp.tools.update import update as update_impl
from rootmem.logging import configure_logging, get_logger
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.repository import PostgresMemoryRepository
from rootmem.storage.protocols import MemoryRepository, NotFoundError


def _validated[ModelT: BaseModel](model: type[ModelT], **kwargs: Any) -> ModelT:
    try:
        return model(**kwargs)
    except PydanticValidationError as exc:
        messages = "; ".join(str(e["msg"]) for e in exc.errors())
        raise ToolError(messages) from exc


def build_server(
    repository: MemoryRepository,
    graph_repository: GraphRepository,
    embedding_provider: EmbeddingProvider,
    extraction_provider: ExtractionProvider,
) -> MCPServer:
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
        return await remember_impl(repository, embedding_provider, params)

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
        mode: str = "hybrid",
    ) -> SearchResponse:
        """Text, semantic, or hybrid (default) search over non-deleted
        memories in a namespace. `mode`: "text" | "semantic" | "hybrid"."""
        params = _validated(
            SearchParams,
            query=query,
            namespace=namespace,
            limit=limit,
            source=source,
            mode=mode,
        )
        return await search_impl(repository, embedding_provider, params)

    @server.tool()
    async def related(
        entity_name: str,
        entity_type: str,
        namespace: str = "default",
        max_hops: int = 1,
    ) -> RelatedResult:
        """Entities/relations connected to a named entity, up to `max_hops`
        hops away — includes superseded (non-active) relations with their
        full bi-temporal history."""
        params = _validated(
            RelatedParams,
            entity_name=entity_name,
            entity_type=entity_type,
            namespace=namespace,
            max_hops=max_hops,
        )
        return await related_impl(graph_repository, params)

    @server.tool()
    async def ingest_session(
        transcript: str,
        source: str,
        namespace: str = "default",
        session_id: str | None = None,
    ) -> IngestSessionResult:
        """Embed and store `transcript` as a memory, then extract entities/
        relations from it into the graph. Both embedding and extraction
        degrade gracefully on failure rather than blocking the write."""
        params = _validated(
            IngestSessionParams,
            transcript=transcript,
            source=source,
            namespace=namespace,
            session_id=session_id,
        )
        return await ingest_session_impl(
            repository, graph_repository, embedding_provider, extraction_provider, params
        )

    return server


def _import_and_construct_voyage_provider(settings: Settings) -> VoyageEmbeddingProvider:
    # The slow `import voyageai` (see module docstring note above) happens
    # here, inside the background thread, on first call only — not at
    # module load time.
    from rootmem.embedding.voyage import VoyageEmbeddingProvider

    return VoyageEmbeddingProvider(settings)


def _import_and_construct_anthropic_provider(settings: Settings) -> AnthropicExtractionProvider:
    from rootmem.extraction.anthropic_provider import AnthropicExtractionProvider

    return AnthropicExtractionProvider(settings)


class _LazyEmbeddingProvider:
    """Defers the `voyageai` import and `VoyageEmbeddingProvider`
    construction to a background thread.

    A real run on this machine measured ~12s for `import voyageai` alone
    (an OS-level, one-time-per-process cost on the first import that pulls
    in the httpx/httpcore/certifi chain — not a network call) plus more for
    constructing the client. Done eagerly in `main_async`, that pushed total
    server startup past MCP clients' ~30s connection timeout, surfacing as
    "Connection closed"/"Failed" with the server never even completing the
    MCP handshake. Starting the import+construction in a thread (so it
    doesn't block the event loop) as early as possible in `main_async`, then
    awaiting it only when a tool actually calls `embed`, lets
    `run_stdio_async()` start accepting the handshake immediately; only the
    *first* real embedding call pays the one-time cost, exactly like
    `EmbeddingError` degradation already accepts a slow/unreliable embedding
    path without failing the surrounding operation.
    """

    def __init__(self, settings: Settings) -> None:
        self._task: asyncio.Task[VoyageEmbeddingProvider] = asyncio.create_task(
            asyncio.to_thread(_import_and_construct_voyage_provider, settings)
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        provider = await self._task
        return await provider.embed(texts)


class _LazyExtractionProvider:
    """Same rationale and mechanism as `_LazyEmbeddingProvider`, for
    `AnthropicExtractionProvider` (`import anthropic` is fast once
    `voyageai` has already paid the shared httpx/certifi one-time cost in
    the same process, but is not guaranteed to run second, so it gets the
    same treatment)."""

    def __init__(self, settings: Settings) -> None:
        self._task: asyncio.Task[AnthropicExtractionProvider] = asyncio.create_task(
            asyncio.to_thread(_import_and_construct_anthropic_provider, settings)
        )

    async def extract(self, text: str, context: ExtractionContext) -> ExtractionResult:
        provider = await self._task
        return await provider.extract(text, context)


async def main_async() -> None:
    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    # Started before `create_pool` is awaited (not after) so their background
    # threads run concurrently with that network wait, not sequentially after it.
    embedding_provider: EmbeddingProvider = _LazyEmbeddingProvider(settings)
    extraction_provider: ExtractionProvider = _LazyExtractionProvider(settings)

    pool = await create_pool(settings)
    try:
        repository = PostgresMemoryRepository(
            pool, settings.hybrid_search_weight_text, settings.hybrid_search_weight_vector
        )
        graph_repository = PostgresGraphRepository(pool, settings.contradiction_confidence_floor)
        server = build_server(repository, graph_repository, embedding_provider, extraction_provider)
        logger.info("rootmem MCP server starting (stdio transport)")
        await server.run_stdio_async()
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
