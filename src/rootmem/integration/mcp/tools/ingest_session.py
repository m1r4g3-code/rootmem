"""`ingest_session` — the in-session equivalent of `capture/cli.py`, for
batch import without leaving an active MCP conversation (FR3,
docs/requirements/phase1-requirements.md). Thin wrapper over
`capture.ingest.ingest_transcript`.
"""

from __future__ import annotations

from rootmem.capture.ingest import ingest_transcript
from rootmem.embedding.protocols import EmbeddingProvider
from rootmem.extraction.protocols import ExtractionProvider
from rootmem.integration.mcp.schemas import IngestSessionParams, IngestSessionResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.protocols import MemoryRepository


@log_operation("ingest_session")
async def ingest_session(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    embedding_provider: EmbeddingProvider,
    extraction_provider: ExtractionProvider,
    params: IngestSessionParams,
) -> IngestSessionResult:
    result = await ingest_transcript(
        memory_repository,
        graph_repository,
        embedding_provider,
        extraction_provider,
        namespace=params.namespace,
        content=params.transcript,
        source=params.source,
        source_session_id=params.session_id,
        importance_flag=params.importance_flag,
        session_outcome=params.session_outcome,
    )
    return IngestSessionResult.from_ingest_result(result)
