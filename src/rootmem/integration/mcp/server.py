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
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from rootmem.config import Settings, get_settings
from rootmem.consolidation.procedural_protocols import (
    ProceduralDistillationContext,
    ProceduralDistillationProvider,
)
from rootmem.consolidation.protocols import DistillationContext, DistillationProvider
from rootmem.consolidation.skill_format import SkillDraft
from rootmem.embedding.protocols import EmbeddingProvider
from rootmem.extraction.contradiction import BayesianSettings
from rootmem.extraction.models import ExtractionContext, ExtractionResult
from rootmem.extraction.protocols import ExtractionProvider

# `voyageai`/`anthropic` are deliberately NOT imported at module level: a real
# run on this machine measured `import voyageai` alone taking ~12s (the
# first import in-process to pull in the httpx/httpcore/certifi chain pays
# some OS-level one-time cost here — see `_LazyEmbeddingProvider` below).
# Importing them at module level would pay that cost before the MCP server
# even starts listening for the handshake, which is the bug being fixed.
if TYPE_CHECKING:
    from rootmem.consolidation.anthropic_distillation_provider import (
        AnthropicDistillationProvider,
    )
    from rootmem.consolidation.anthropic_procedural_distillation_provider import (
        AnthropicProceduralDistillationProvider,
    )
    from rootmem.embedding.voyage import VoyageEmbeddingProvider
    from rootmem.extraction.anthropic_provider import AnthropicExtractionProvider
from rootmem.audit.recorder import AuditRecorder, content_sha256
from rootmem.integration.mcp.schemas import (
    ConsolidateParams,
    ConsolidateResult,
    FeedbackParams,
    FeedbackResult,
    FindSkillParams,
    FindSkillResult,
    ForgetParams,
    ForgetResult,
    GetSkillParams,
    GetSkillResult,
    IngestSessionParams,
    IngestSessionResult,
    RecallParams,
    RecallResult,
    RelatedParams,
    RelatedResult,
    RememberParams,
    RememberResult,
    ReportSkillOutcomeParams,
    ReportSkillOutcomeResult,
    SearchParams,
    SearchResponse,
    UpdateParams,
    UpdateResult,
    VerifyAuditParams,
    VerifyAuditResult,
)
from rootmem.integration.mcp.tools.consolidate import consolidate as consolidate_impl
from rootmem.integration.mcp.tools.feedback import feedback as feedback_impl
from rootmem.integration.mcp.tools.find_skill import find_skill as find_skill_impl
from rootmem.integration.mcp.tools.forget import forget as forget_impl
from rootmem.integration.mcp.tools.get_skill import get_skill as get_skill_impl
from rootmem.integration.mcp.tools.ingest_session import ingest_session as ingest_session_impl
from rootmem.integration.mcp.tools.recall import recall as recall_impl
from rootmem.integration.mcp.tools.related import related as related_impl
from rootmem.integration.mcp.tools.remember import remember as remember_impl
from rootmem.integration.mcp.tools.report_skill_outcome import (
    report_skill_outcome as report_skill_outcome_impl,
)
from rootmem.integration.mcp.tools.search import search as search_impl
from rootmem.integration.mcp.tools.update import update as update_impl
from rootmem.integration.mcp.tools.verify_audit import verify_audit as verify_audit_impl
from rootmem.logging import configure_logging, get_logger
from rootmem.retrieval.rerank import RankingContext
from rootmem.storage.audit_protocols import AuditLogRepository
from rootmem.storage.consolidation_protocols import ConsolidationRepository
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.postgres.audit_repository import PostgresAuditLogRepository
from rootmem.storage.postgres.connection import create_pool
from rootmem.storage.postgres.consolidation_repository import PostgresConsolidationRepository
from rootmem.storage.postgres.graph_repository import PostgresGraphRepository
from rootmem.storage.postgres.procedural_repository import PostgresProceduralMemoryRepository
from rootmem.storage.postgres.repository import PostgresMemoryRepository
from rootmem.storage.procedural_protocols import ProceduralMemoryRepository
from rootmem.storage.protocols import MemoryRepository, NotFoundError, StorageError


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
    consolidation_repository: ConsolidationRepository,
    distillation_provider: DistillationProvider,
    procedural_memory_repository: ProceduralMemoryRepository,
    procedural_distillation_provider: ProceduralDistillationProvider,
    settings: Settings,
    audit_repository: AuditLogRepository | None = None,
) -> MCPServer:
    server = MCPServer(name="rootmem")
    ranking = RankingContext.from_settings(settings)
    audit = AuditRecorder(audit_repository, settings.audit_actor)

    async def audit_record(
        namespace: str,
        action: str,
        target_type: str,
        target_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append an audit entry after a mutation. An operation that cannot
        be audited is reported as an error (ADR 0025, NFR6), never left
        silently unaudited."""
        try:
            await audit.record(namespace, action, target_type, target_id, payload)
        except StorageError as exc:
            raise ToolError(f"{action} applied but audit append failed: {exc}") from exc

    # Held so a fire-and-forget asyncio.Task isn't garbage-collected mid-
    # flight (a real, documented asyncio pitfall) -- discarded on completion
    # via the done_callback below. See NFR10, docs/requirements/
    # phase2-requirements.md.
    background_tasks: set[asyncio.Task[None]] = set()

    @server.tool()
    async def remember(
        content: str,
        source: str,
        namespace: str = "default",
        key: str | None = None,
        source_session_id: str | None = None,
        confidence: float = 1.0,
        importance_flag: float = 0.0,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RememberResult:
        """Persist a new memory. If `idempotency_key` collides with an existing,
        non-deleted memory in the same namespace, returns that memory instead
        of creating a duplicate. `importance_flag` (0-1) is a cheap, optional
        input to salience scoring, applied later during consolidation."""
        params = _validated(
            RememberParams,
            content=content,
            source=source,
            namespace=namespace,
            key=key,
            source_session_id=source_session_id,
            confidence=confidence,
            importance_flag=importance_flag,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )
        remembered = await remember_impl(repository, embedding_provider, params)
        await audit_record(
            namespace,
            "remember",
            "memory",
            remembered.id,
            {"source": source, "key": key, "content_sha256": content_sha256(content)},
        )
        return remembered

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
            updated = await update_impl(repository, params)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc
        await audit_record(
            updated.namespace,
            "update",
            "memory",
            updated.id,
            {
                "fields": sorted(
                    field
                    for field, value in (
                        ("content", content),
                        ("confidence", confidence),
                        ("metadata", metadata),
                    )
                    if value is not None
                ),
                "content_sha256": content_sha256(content) if content is not None else None,
            },
        )
        return updated

    @server.tool()
    async def forget(id: str, reason: str | None = None) -> ForgetResult:
        """Soft-delete a memory. Idempotent: forgetting an already-deleted
        memory succeeds and returns its existing deletion timestamp."""
        params = _validated(ForgetParams, id=id, reason=reason)
        try:
            forgotten = await forget_impl(repository, params)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc
        await audit_record(
            forgotten.namespace, "forget", "memory", forgotten.id, {"reason": reason}
        )
        return forgotten

    @server.tool()
    async def search(
        query: str,
        namespace: str = "default",
        limit: int = 10,
        source: str | None = None,
        mode: str = "hybrid",
        entity_name: str | None = None,
        entity_type: str | None = None,
        as_of: datetime | None = None,
    ) -> SearchResponse:
        """Text, semantic, or hybrid (default) search over non-deleted
        memories in a namespace, re-ranked by relevance, retention (decay),
        salience, source trust and graph proximity; each result carries a
        per-term `breakdown`. `mode`: "text" | "semantic" | "hybrid".
        Naming an `entity_name`+`entity_type` lifts memories linked to it.
        `as_of` scores retention at that instant without recording access."""
        params = _validated(
            SearchParams,
            query=query,
            namespace=namespace,
            limit=limit,
            source=source,
            mode=mode,
            entity_name=entity_name,
            entity_type=entity_type,
            as_of=as_of,
        )
        return await search_impl(
            repository,
            embedding_provider,
            params,
            ranking=ranking,
            graph_repository=graph_repository,
        )

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
        importance_flag: float = 0.0,
        session_outcome: str | None = None,
    ) -> IngestSessionResult:
        """Embed and store `transcript` as a memory, then extract entities/
        relations from it into the graph. Both embedding and extraction
        degrade gracefully on failure rather than blocking the write.
        `importance_flag` (0-1) is a cheap, optional input to salience
        scoring, applied later during consolidation. `session_outcome`
        ("success" | "failure") is a cheap, optional signal feeding
        episodic->procedural/failure->lesson distillation's session
        grouping -- pass it when `session_id` identifies an ordered,
        multi-step task attempt whose outcome is known."""
        params = _validated(
            IngestSessionParams,
            transcript=transcript,
            source=source,
            namespace=namespace,
            session_id=session_id,
            importance_flag=importance_flag,
            session_outcome=session_outcome,
        )
        result = await ingest_session_impl(
            repository, graph_repository, embedding_provider, extraction_provider, params
        )
        await audit_record(
            namespace,
            "ingest_session",
            "memory",
            result.memory_id,
            {
                "source": source,
                "session_id": session_id,
                "session_outcome": session_outcome,
                "content_sha256": content_sha256(transcript),
                "superseded_count": result.superseded_count,
                "contested_count": result.contested_count,
            },
        )

        # Inline auto-trigger (ADR 0012, FR3): check the consolidation
        # trigger and, if met, run it in the background -- never blocking
        # ingest_session's own return on a potentially-slow pass. A failure
        # here is a background-task concern, not this call's: log and move
        # on, never let it surface as ingest_session's own error.
        async def _maybe_consolidate() -> None:
            from rootmem.consolidation.distill import maybe_run_consolidation

            try:
                await maybe_run_consolidation(
                    repository,
                    graph_repository,
                    consolidation_repository,
                    distillation_provider,
                    embedding_provider,
                    procedural_memory_repository,
                    procedural_distillation_provider,
                    namespace,
                    settings,
                )
            except Exception as exc:  # noqa: BLE001 - background task, must never crash the server
                get_logger().warning(
                    "operation=consolidate_auto_trigger outcome=error error=%s", exc
                )

        task = asyncio.create_task(_maybe_consolidate())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

        return result

    @server.tool()
    async def consolidate(namespace: str = "default", force: bool = False) -> ConsolidateResult:
        """Run one consolidation pass on demand: checks the trigger
        condition (episode count or time elapsed) unless `force=True`
        bypasses it, and no-ops cleanly (`ran: false`) when unmet."""
        params = _validated(ConsolidateParams, namespace=namespace, force=force)
        consolidated = await consolidate_impl(
            repository,
            graph_repository,
            consolidation_repository,
            distillation_provider,
            embedding_provider,
            procedural_memory_repository,
            procedural_distillation_provider,
            settings,
            params,
        )
        if consolidated.ran:
            await audit_record(
                namespace,
                "consolidate",
                "consolidation_run",
                None,
                consolidated.model_dump(mode="json"),
            )
        return consolidated

    @server.tool()
    async def feedback(
        relation_id: str,
        outcome: str,
        namespace: str = "default",
        confidence: float = 1.0,
        note: str | None = None,
    ) -> FeedbackResult:
        """Report whether a relation turned out to be correct
        (`outcome="confirmed"`) or wrong (`outcome="contradicted"`) --
        the retrieval-outcome feedback that updates its Bayesian belief."""
        params = _validated(
            FeedbackParams,
            relation_id=relation_id,
            outcome=outcome,
            namespace=namespace,
            confidence=confidence,
            note=note,
        )
        try:
            fed_back = await feedback_impl(graph_repository, params)
        except NotFoundError as exc:
            raise ToolError(str(exc)) from exc
        await audit_record(
            namespace,
            "feedback",
            "relation",
            relation_id,
            {"outcome": outcome, "confidence": confidence, "note": note},
        )
        return fed_back

    @server.tool()
    async def find_skill(
        query: str,
        namespace: str = "default",
        kind: str = "all",
        limit: int = 10,
    ) -> FindSkillResult:
        """Hybrid text+vector search over distilled procedural memories
        (skills/lessons), ranked by real content -- not name-matching.
        `kind`: "skill" | "lesson" | "all"."""
        params = _validated(
            FindSkillParams, query=query, namespace=namespace, kind=kind, limit=limit
        )
        return await find_skill_impl(
            procedural_memory_repository, embedding_provider, params, ranking=ranking
        )

    @server.tool()
    async def get_skill(name: str, namespace: str = "default") -> GetSkillResult:
        """Retrieve one named, active procedural memory as literal
        SKILL.md-conformant markdown text (frontmatter + body). Returns
        `found: false` (not an error) if no matching skill/lesson exists.
        Installing the returned content anywhere is the caller's job --
        this server never writes to any filesystem skills directory."""
        params = _validated(GetSkillParams, name=name, namespace=namespace)
        return await get_skill_impl(procedural_memory_repository, params)

    @server.tool()
    async def report_skill_outcome(
        name: str, success: bool, namespace: str = "default"
    ) -> ReportSkillOutcomeResult:
        """Report that applying the named skill/lesson worked (`success=true`)
        or did not. Updates its effectiveness, which feeds `find_skill`'s
        ranking. Explicit by design: nothing infers this signal."""
        params = _validated(
            ReportSkillOutcomeParams, name=name, namespace=namespace, success=success
        )
        outcome = await report_skill_outcome_impl(
            procedural_memory_repository,
            params,
            reliability=settings.bayesian_source_reliability_feedback,
            prior_strength=settings.bayesian_prior_strength,
        )
        if outcome.found:
            await audit_record(
                namespace,
                "report_skill_outcome",
                "procedural_memory",
                name,
                {"success": success, "applied_count": outcome.applied_count},
            )
        return outcome

    @server.tool()
    async def verify_audit(namespace: str = "default") -> VerifyAuditResult:
        """Recompute the namespace's tamper-evident audit hash chain and
        report whether it is intact, or the first altered/missing entry."""
        params = _validated(VerifyAuditParams, namespace=namespace)
        return await verify_audit_impl(audit_repository, params)

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


def _import_and_construct_distillation_provider(
    settings: Settings,
) -> AnthropicDistillationProvider:
    from rootmem.consolidation.anthropic_distillation_provider import (
        AnthropicDistillationProvider,
    )

    return AnthropicDistillationProvider(settings)


def _import_and_construct_procedural_distillation_provider(
    settings: Settings,
) -> AnthropicProceduralDistillationProvider:
    from rootmem.consolidation.anthropic_procedural_distillation_provider import (
        AnthropicProceduralDistillationProvider,
    )

    return AnthropicProceduralDistillationProvider(settings)


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


class _LazyDistillationProvider:
    """Same rationale and mechanism as `_LazyEmbeddingProvider`/
    `_LazyExtractionProvider`, for `AnthropicDistillationProvider` (also
    constructs an `anthropic.AsyncAnthropic` client, so it carries the same
    slow-first-import risk)."""

    def __init__(self, settings: Settings) -> None:
        self._task: asyncio.Task[AnthropicDistillationProvider] = asyncio.create_task(
            asyncio.to_thread(_import_and_construct_distillation_provider, settings)
        )

    async def distill(self, texts: list[str], context: DistillationContext) -> ExtractionResult:
        provider = await self._task
        return await provider.distill(texts, context)


class _LazyProceduralDistillationProvider:
    """Same rationale and mechanism as `_LazyEmbeddingProvider`/
    `_LazyDistillationProvider`, for `AnthropicProceduralDistillationProvider`
    (also constructs an `anthropic.AsyncAnthropic` client)."""

    def __init__(self, settings: Settings) -> None:
        self._task: asyncio.Task[AnthropicProceduralDistillationProvider] = asyncio.create_task(
            asyncio.to_thread(_import_and_construct_procedural_distillation_provider, settings)
        )

    async def distill_procedure(
        self, traces: list[list[str]], context: ProceduralDistillationContext
    ) -> SkillDraft:
        provider = await self._task
        return await provider.distill_procedure(traces, context)


async def main_async() -> None:
    settings = get_settings()
    configure_logging(settings.rootmem_log_level)
    logger = get_logger()

    # Started before `create_pool` is awaited (not after) so their background
    # threads run concurrently with that network wait, not sequentially after it.
    embedding_provider: EmbeddingProvider = _LazyEmbeddingProvider(settings)
    extraction_provider: ExtractionProvider = _LazyExtractionProvider(settings)
    distillation_provider: DistillationProvider = _LazyDistillationProvider(settings)
    procedural_distillation_provider: ProceduralDistillationProvider = (
        _LazyProceduralDistillationProvider(settings)
    )

    pool = await create_pool(settings)
    try:
        repository = PostgresMemoryRepository(
            pool, settings.hybrid_search_weight_text, settings.hybrid_search_weight_vector
        )
        graph_repository = PostgresGraphRepository(pool, BayesianSettings.from_settings(settings))
        consolidation_repository = PostgresConsolidationRepository(pool)
        procedural_memory_repository = PostgresProceduralMemoryRepository(pool)
        audit_repository = PostgresAuditLogRepository(pool)
        server = build_server(
            repository,
            graph_repository,
            embedding_provider,
            extraction_provider,
            consolidation_repository,
            distillation_provider,
            procedural_memory_repository,
            procedural_distillation_provider,
            settings,
            audit_repository,
        )
        logger.info("rootmem MCP server starting (stdio transport)")
        await server.run_stdio_async()
    finally:
        await pool.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
