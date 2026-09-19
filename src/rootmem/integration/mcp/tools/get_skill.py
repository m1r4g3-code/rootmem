"""`get_skill` — retrieve one named, active procedural memory as literal
SKILL.md-conformant markdown text (ADR 0018). ROOTMEM's entire contract for
a skill ends at this response; "installing" it anywhere is the calling
agent's/human's job, not this server's.
"""

from __future__ import annotations

from rootmem.consolidation.skill_format import SkillDraft, render_skill_markdown
from rootmem.integration.mcp.schemas import GetSkillParams, GetSkillResult
from rootmem.observability.metrics import log_operation
from rootmem.storage.procedural_protocols import ProceduralMemoryRepository


@log_operation("get_skill")
async def get_skill(
    procedural_memory_repository: ProceduralMemoryRepository, params: GetSkillParams
) -> GetSkillResult:
    record = await procedural_memory_repository.get_by_name(params.namespace, params.name)
    if record is None:
        return GetSkillResult(found=False)
    markdown = render_skill_markdown(
        SkillDraft(
            name=record.name, description=record.description, body_markdown=record.body_markdown
        )
    )
    return GetSkillResult(found=True, kind=record.kind, markdown=markdown)
