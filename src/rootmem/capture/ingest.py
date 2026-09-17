"""Ingestion orchestration: turn a raw transcript into a stored `memories`
row, an embedding, and graph entities/relations — the write path `capture`
provides alongside `remember`'s direct, explicit-content path (see
src/rootmem/capture/README.md's Phase 0 note: "Phase 0's `remember` MCP tool
is the only write path today; there is no automatic capture yet." This is
that capture).

Pure orchestration, dependency-injected exactly like `remember.py`
(ADR 0003's pattern extended to the four new ports this phase adds) — fully
unit-testable against fakes with zero I/O, wired to real adapters only in
`server.py`/`capture/cli.py`.
"""

from __future__ import annotations

from rootmem.embedding.protocols import EmbeddingProvider, embed_or_none
from rootmem.extraction.models import ExtractionContext
from rootmem.extraction.pipeline import apply_extraction
from rootmem.extraction.protocols import ExtractionError, ExtractionProvider
from rootmem.logging import get_logger
from rootmem.storage.graph_protocols import GraphRepository
from rootmem.storage.models import NewMemory
from rootmem.storage.protocols import MemoryRepository

from .models import IngestResult


async def ingest_transcript(
    memory_repository: MemoryRepository,
    graph_repository: GraphRepository,
    embedding_provider: EmbeddingProvider,
    extraction_provider: ExtractionProvider,
    namespace: str,
    content: str,
    source: str,
    source_session_id: str | None = None,
    importance_flag: float = 0.0,
) -> IngestResult:
    """Embed and store `content` as a memory, then extract entities/relations
    from it into the graph. Both the embedding call and the extraction call
    degrade gracefully on failure (NFR2, docs/requirements/phase1-requirements.md)
    — an external-API outage never blocks the memory from being stored.
    `importance_flag` (Phase 2, FR1) is a cheap, optional input to salience
    scoring, applied at consolidation time, not here."""
    embedding = await embed_or_none(embedding_provider, content)

    memory = await memory_repository.create(
        NewMemory(
            namespace=namespace,
            content=content,
            content_embedding=embedding,
            source=source,
            source_session_id=source_session_id,
            importance_flag=importance_flag,
        )
    )

    try:
        extraction_result = await extraction_provider.extract(
            content,
            ExtractionContext(
                namespace=namespace, source=source, source_session_id=source_session_id
            ),
        )
    except ExtractionError as exc:
        get_logger().warning("operation=extract outcome=degraded error=%s", exc)
        return IngestResult(
            memory_id=memory.id,
            embedded=embedding is not None,
            entities_extracted=0,
            relations_extracted=0,
            superseded_count=0,
            contested_count=0,
            extraction_degraded=True,
        )

    apply_result = await apply_extraction(
        graph_repository, namespace, extraction_result, source_memory_ids=[memory.id]
    )

    superseded_count = sum(
        1 for r in apply_result.resolutions if r.previous is not None and not r.contested
    )
    contested_count = sum(1 for r in apply_result.resolutions if r.contested)

    return IngestResult(
        memory_id=memory.id,
        embedded=embedding is not None,
        entities_extracted=len(apply_result.entity_ids),
        relations_extracted=len(apply_result.resolutions),
        superseded_count=superseded_count,
        contested_count=contested_count,
        extraction_degraded=False,
    )
