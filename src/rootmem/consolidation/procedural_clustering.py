"""Session-trace grouping and cross-session similarity-pair construction for
episodic->procedural distillation (ADR 0017). Pure functions, zero I/O --
`consolidation.distill`'s orchestration fetches episodes and calls
`EmbeddingProvider.embed` on each qualifying trace's summary text, then hands
the resulting embeddings to `build_trace_pairs`, whose output feeds
`consolidation.clustering.cluster_by_similarity` (reused unmodified).

Full derivation: docs/math-spec/phase3-math-spec.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING, Literal

from rootmem.retrieval.ranking import cosine_similarity

if TYPE_CHECKING:
    from rootmem.storage.models import MemoryRecord


@dataclass(frozen=True)
class SessionTrace:
    session_id: str
    outcome: Literal["success", "failure"]
    memory_ids: list[str]
    # Ordered step texts (one per source episode) -- the shape
    # `ProceduralDistillationProvider.distill_procedure` wants, since an LLM
    # benefits from seeing the step structure, not a pre-flattened blob.
    steps: list[str]
    # Newline-joined `steps` -- the one input `EmbeddingProvider.embed` wants
    # for trace-level similarity (ADR 0017). Kept alongside `steps` rather
    # than re-joined at each call site.
    summary_text: str


def group_session_traces(
    episodes: list[MemoryRecord], *, min_session_length: int
) -> list[SessionTrace]:
    """Group episodes sharing `(source_session_id, session_outcome)` into
    ordered session traces (by `created_at`), joined into one newline-joined
    summary text per trace. Episodes with no `source_session_id` or no
    `session_outcome` are never grouped -- a "procedure" requires both the
    ordered-sequence and outcome structure only `ingest_session` provides.
    Groups smaller than `min_session_length` are dropped -- a single episode
    has no internal sequence to summarize as a multi-step trace."""
    groups: dict[tuple[str, Literal["success", "failure"]], list[MemoryRecord]] = {}
    for episode in episodes:
        if episode.source_session_id is None or episode.session_outcome is None:
            continue
        key = (episode.source_session_id, episode.session_outcome)
        groups.setdefault(key, []).append(episode)

    traces: list[SessionTrace] = []
    for (session_id, outcome), members in groups.items():
        if len(members) < min_session_length:
            continue
        ordered = sorted(members, key=lambda m: m.created_at)
        steps = [m.content for m in ordered]
        traces.append(
            SessionTrace(
                session_id=session_id,
                outcome=outcome,
                memory_ids=[m.id for m in ordered],
                steps=steps,
                summary_text="\n".join(steps),
            )
        )
    return traces


def build_trace_pairs(
    trace_embeddings: dict[str, list[float]],
) -> list[tuple[str, str, float]]:
    """`(session_id, session_id, cosine_similarity)` triples for every pair
    of trace embeddings -- the exact input shape
    `consolidation.clustering.cluster_by_similarity` expects, reused
    unmodified (ADR 0017)."""
    return [
        (a, b, cosine_similarity(trace_embeddings[a], trace_embeddings[b]))
        for a, b in combinations(trace_embeddings, 2)
    ]
