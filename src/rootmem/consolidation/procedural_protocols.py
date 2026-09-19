"""The procedural distillation port: `ProceduralDistillationProvider`.

A new, separate Protocol from `DistillationProvider` (ADR 0020), not an
extension of it: `DistillationProvider.distill`'s output, `ExtractionResult`,
is entities-and-relations-shaped; procedural distillation's output is a
`SkillDraft` (name/description/body) with no entities or relations in it at
all -- a genuinely different aggregate, per the same "different aggregate ->
different Protocol" test ADR 0006 already applies to storage Protocols,
applied here to a provider Protocol (ADR 0009 already established this isn't
storage-specific: `EmbeddingProvider`/`ExtractionProvider` are themselves
separate Protocols).
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from rootmem.consolidation.skill_format import SkillDraft

__all__ = [
    "ProceduralDistillationContext",
    "ProceduralDistillationError",
    "ProceduralDistillationProvider",
    "SkillDraft",
]


class ProceduralDistillationError(Exception):
    """Raised when the procedural distillation provider is unreachable,
    rejects a request, or returns output that doesn't parse into
    `SkillDraft`."""


class ProceduralDistillationContext(BaseModel):
    namespace: str
    kind: Literal["skill", "lesson"]


class ProceduralDistillationProvider(Protocol):
    async def distill_procedure(
        self, traces: list[list[str]], context: ProceduralDistillationContext
    ) -> SkillDraft:
        """Abstract a named, reusable procedure (`kind="skill"`) from several
        ordered, same-outcome session traces, or a cautionary lesson
        (`kind="lesson"`) from a single failed trace. `traces` is one list of
        ordered step texts per session -- `len(traces) >= 2` for a skill
        (ADR 0017's recurrence gate), exactly `1` for a lesson. Raises
        `ProceduralDistillationError` on failure -- never returns a partial
        result silently."""
        ...
