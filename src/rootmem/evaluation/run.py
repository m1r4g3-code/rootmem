"""Offline retrieval evaluation (ADR 0039): compares lexical, semantic and
Phase 4 multi-factor ranking on the labeled set in `dataset.py`.

Deterministic and offline: embeddings come from a recorded fixture and time is
a fixed instant, so the same inputs always give the same numbers.

Honest limits, repeated in the report: the set is small and synthetic; the
"semantic" baseline here is cosine similarity over the in-memory repository,
not the production Postgres hybrid (whose text component is `ts_rank`); and a
weight grid over 15 queries can overfit, so it informs a decision, it does not
make one.

    python -m rootmem.evaluation.run --out docs/benchmarks/phase6-retrieval-eval.md
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rootmem.embedding.fakes.fixture_provider import FixtureReplayEmbeddingProvider
from rootmem.evaluation.dataset import MEMORIES, QUERIES, TRUST_BY_SOURCE, EvalQuery
from rootmem.evaluation.metrics import mean, ndcg_at_k, recall_at_k, reciprocal_rank
from rootmem.retrieval.decay import RetentionParams
from rootmem.retrieval.ranking import RankWeights
from rootmem.retrieval.rerank import RankingContext, rerank_memory_hits
from rootmem.storage.fakes.in_memory_graph_repository import InMemoryGraphRepository
from rootmem.storage.fakes.in_memory_repository import InMemoryMemoryRepository
from rootmem.storage.graph_models import EntityRecord, NewEntity
from rootmem.storage.models import MemoryRecord, SearchResult
from rootmem.trust.scoring import TrustParams

NAMESPACE = "eval"
K = 5
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
DEFAULT_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "eval_embeddings.json"
)
DEFAULT_WEIGHTS = RankWeights()


@dataclass
class QueryScore:
    recall: float
    mrr: float
    ndcg: float


@dataclass
class VariantResult:
    name: str
    per_query: dict[str, QueryScore] = field(default_factory=dict)

    def mean_of(self, attribute: str, kinds: set[str] | None = None) -> float:
        values = [
            getattr(score, attribute)
            for qid, score in self.per_query.items()
            if kinds is None or _KIND_BY_QUERY[qid] in kinds
        ]
        return mean(values)


@dataclass
class GridRow:
    retention_weight: float
    trust_weight: float
    ndcg: float
    mrr: float


@dataclass
class Report:
    variants: list[VariantResult]
    grid: list[GridRow]
    query_count: int
    memory_count: int


_KIND_BY_QUERY = {q.id: q.kind for q in QUERIES}


@dataclass
class _World:
    repository: InMemoryMemoryRepository
    graph: InMemoryGraphRepository
    provider: FixtureReplayEmbeddingProvider
    entities: dict[tuple[str, str], EntityRecord]


async def _build_world(fixture_path: Path) -> _World:
    provider = FixtureReplayEmbeddingProvider(fixture_path)
    embeddings = await provider.embed([m.content for m in MEMORIES])
    repository = InMemoryMemoryRepository()
    graph = InMemoryGraphRepository()
    entities: dict[tuple[str, str], EntityRecord] = {}
    for memory, embedding in zip(MEMORIES, embeddings, strict=True):
        created = NOW - timedelta(days=memory.age_days)
        last_accessed = (
            NOW - timedelta(days=max(1, memory.age_days // 4)) if memory.access_count else None
        )
        repository._records[memory.id] = MemoryRecord(
            id=memory.id,
            namespace=NAMESPACE,
            content=memory.content,
            content_embedding=embedding,
            source=memory.source,
            confidence=1.0,
            salience_score=memory.salience,
            last_accessed_at=last_accessed,
            access_count=memory.access_count,
            created_at=created,
            updated_at=created,
        )
        if memory.entity is not None:
            if memory.entity not in entities:
                entities[memory.entity] = await graph.upsert_entity(
                    NewEntity(
                        namespace=NAMESPACE, entity_type=memory.entity[0], name=memory.entity[1]
                    )
                )
            await graph.link_memory_entity(memory.id, entities[memory.entity].id)
    return _World(repository, graph, provider, entities)


def _score(ranked_ids: list[str], query: EvalQuery) -> QueryScore:
    return QueryScore(
        recall=recall_at_k(ranked_ids, query.relevance, K),
        mrr=reciprocal_rank(ranked_ids, query.relevance),
        ndcg=ndcg_at_k(ranked_ids, query.relevance, K),
    )


def _context(weights: RankWeights) -> RankingContext:
    return RankingContext(
        weights=weights,
        retention=RetentionParams(base_stability_days=7.0),
        trust=TrustParams(default_reliability=0.5, source_reliability=TRUST_BY_SOURCE),
    )


async def _semantic_candidates(world: _World, query: EvalQuery) -> list[SearchResult]:
    (embedding,) = await world.provider.embed([query.text])
    return await world.repository.search_semantic(NAMESPACE, embedding, 30)


async def _evaluate_multifactor(world: _World, name: str, weights: RankWeights) -> VariantResult:
    result = VariantResult(name)
    context = _context(weights)
    for query in QUERIES:
        candidates = await _semantic_candidates(world, query)
        entity = world.entities.get(query.entity) if query.entity else None
        ranked = await rerank_memory_hits(candidates, NAMESPACE, context, NOW, world.graph, entity)
        result.per_query[query.id] = _score([hit.record.id for hit, _ in ranked], query)
    return result


async def evaluate(fixture_path: Path = DEFAULT_FIXTURE) -> Report:
    world = await _build_world(fixture_path)

    lexical = VariantResult("lexical (term match)")
    semantic = VariantResult("semantic (cosine)")
    for query in QUERIES:
        text_hits = await world.repository.search_text(NAMESPACE, query.text, 30)
        lexical.per_query[query.id] = _score([h.record.id for h in text_hits], query)
        semantic_hits = await _semantic_candidates(world, query)
        semantic.per_query[query.id] = _score([h.record.id for h in semantic_hits], query)

    default = await _evaluate_multifactor(world, "multi-factor (Phase 4 defaults)", DEFAULT_WEIGHTS)

    grid: list[GridRow] = []
    for retention_w, trust_w in itertools.product((0.0, 0.1, 0.15, 0.2, 0.3), repeat=2):
        weights = RankWeights(
            relevance=DEFAULT_WEIGHTS.relevance,
            retention=retention_w,
            salience=DEFAULT_WEIGHTS.salience,
            trust=trust_w,
            graph_proximity=DEFAULT_WEIGHTS.graph_proximity,
        )
        variant = await _evaluate_multifactor(world, "grid", weights)
        grid.append(GridRow(retention_w, trust_w, variant.mean_of("ndcg"), variant.mean_of("mrr")))
    return Report([lexical, semantic, default], grid, len(QUERIES), len(MEMORIES))


def render_markdown(report: Report) -> str:
    kinds = ["semantic", "freshness", "trust", "entity"]
    lines = [
        "# Phase 6 retrieval evaluation",
        "",
        "Generated by `python -m rootmem.evaluation.run` (ADR 0039). Not a release gate.",
        "",
        "## Read this first",
        "",
        f"- **Small and synthetic:** {report.memory_count} hand-written memories and "
        f"{report.query_count} queries for a fictional team. Some queries are built so recency, "
        "trust or an explicit entity separates the right answer from a plausible wrong one, so "
        "the set assumes those signals matter; it cannot say how often they do in real use.",
        "- **Direction, not significance:** with 15 queries a difference of one or two rank "
        "positions moves the means. No significance claim is made.",
        '- **Baseline is not production hybrid:** "semantic" is cosine similarity over the '
        "in-memory repository; production blends `ts_rank` with cosine in SQL.",
        "- **The weight grid can overfit** 15 queries; it informs a decision, it does not "
        "make one.",
        "",
        f"Metrics at k={K}: recall@{K}, MRR, nDCG@{K}; means over queries.",
        "",
        "## Overall",
        "",
        f"| Variant | recall@{K} | MRR | nDCG@{K} |",
        "|---|---|---|---|",
    ]
    for v in report.variants:
        lines.append(
            f"| {v.name} | {v.mean_of('recall'):.3f} | {v.mean_of('mrr'):.3f} | "
            f"{v.mean_of('ndcg'):.3f} |"
        )
    lines += ["", "## By query kind (nDCG@5)", "", "| Variant | " + " | ".join(kinds) + " |"]
    lines.append("|---|" + "---|" * len(kinds))
    for v in report.variants:
        cells = " | ".join(f"{v.mean_of('ndcg', {kind}):.3f}" for kind in kinds)
        lines.append(f"| {v.name} | {cells} |")
    per_kind_counts = {kind: sum(1 for q in QUERIES if q.kind == kind) for kind in kinds}
    lines += [
        "",
        "Queries per kind: " + ", ".join(f"{k}={n}" for k, n in per_kind_counts.items()),
        "",
    ]

    semantic_variant, multifactor_variant = report.variants[1], report.variants[2]
    regressions = [
        (q, semantic_variant.per_query[q.id].ndcg, multifactor_variant.per_query[q.id].ndcg)
        for q in QUERIES
        if multifactor_variant.per_query[q.id].ndcg < semantic_variant.per_query[q.id].ndcg
    ]
    lines += ["## Queries where multi-factor ranks worse than plain semantic", ""]
    if regressions:
        lines += ["| Query | kind | semantic nDCG | multi-factor nDCG |", "|---|---|---|---|"]
        for query, before, after in regressions:
            lines.append(
                f"| {query.id}: {query.text} | {query.kind} | {before:.3f} | {after:.3f} |"
            )
    else:
        lines.append("None.")
    lines.append("")

    ordered = sorted(report.grid, key=lambda row: (-row.ndcg, -row.mrr))
    default_row = next(
        row
        for row in report.grid
        if row.retention_weight == DEFAULT_WEIGHTS.retention
        and row.trust_weight == DEFAULT_WEIGHTS.trust
    )
    lines += [
        "## Weight grid (retention x trust, other weights at default)",
        "",
        "| retention | trust | nDCG@5 | MRR |",
        "|---|---|---|---|",
    ]
    for row in ordered[:5]:
        lines.append(
            f"| {row.retention_weight:.2f} | {row.trust_weight:.2f} | "
            f"{row.ndcg:.3f} | {row.mrr:.3f} |"
        )
    lines += [
        "",
        f"Top 5 of {len(report.grid)} shown. Phase 4 defaults (retention "
        f"{DEFAULT_WEIGHTS.retention}, trust {DEFAULT_WEIGHTS.trust}) score nDCG "
        f"{default_row.ndcg:.3f}, MRR {default_row.mrr:.3f}; best in grid: nDCG "
        f"{ordered[0].ndcg:.3f}.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    markdown = render_markdown(asyncio.run(evaluate(args.fixture)))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
