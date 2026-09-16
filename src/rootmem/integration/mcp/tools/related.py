"""`related` — entities/relations connected to a named entity, up to
`max_hops` hops away, including superseded (non-active) relations with
their full bi-temporal history (FR4, docs/requirements/phase1-requirements.md).
"""

from __future__ import annotations

from rootmem.integration.mcp.schemas import RelatedParams, RelatedResult, RelationView
from rootmem.observability.metrics import log_operation
from rootmem.storage.graph_protocols import GraphRepository


@log_operation("related")
async def related(graph_repository: GraphRepository, params: RelatedParams) -> RelatedResult:
    entity = await graph_repository.find_entity_by_name(
        params.namespace, params.entity_type, params.entity_name
    )
    if entity is None:
        return RelatedResult(entity_found=False)

    relations = await graph_repository.related(
        params.namespace, entity.id, max_hops=params.max_hops
    )
    return RelatedResult(
        entity_found=True,
        entity_id=entity.id,
        relations=[RelationView.from_record(r) for r in relations],
    )
