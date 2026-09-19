"""The evaluation harness (ADR 0039). These tests check that it is well
formed and deterministic; they deliberately assert NOTHING about how good the
ranking is, because that is a finding, not a gate."""

from __future__ import annotations

import json

from rootmem.evaluation.dataset import MEMORIES, QUERIES, TRUST_BY_SOURCE
from rootmem.evaluation.run import DEFAULT_FIXTURE, evaluate, render_markdown


def test_every_relevance_label_points_at_a_real_memory() -> None:
    memory_ids = {m.id for m in MEMORIES}
    assert len(memory_ids) == len(MEMORIES)
    for query in QUERIES:
        assert query.relevance, query.id
        assert set(query.relevance) <= memory_ids, query.id
        assert all(grade > 0 for grade in query.relevance.values())


def test_sources_and_entities_are_consistent() -> None:
    assert {m.source for m in MEMORIES} <= set(TRUST_BY_SOURCE)
    linked = {m.entity for m in MEMORIES if m.entity}
    for query in QUERIES:
        if query.entity is not None:
            assert query.entity in linked, query.id
    assert {q.kind for q in QUERIES} == {"semantic", "freshness", "trust", "entity"}


def test_the_recorded_fixture_covers_every_text() -> None:
    recorded = json.loads(DEFAULT_FIXTURE.read_text())["embeddings"]
    for text in [m.content for m in MEMORIES] + [q.text for q in QUERIES]:
        assert text in recorded, text


async def test_evaluation_is_deterministic_and_scores_are_valid() -> None:
    first = await evaluate()
    second = await evaluate()

    assert render_markdown(first) == render_markdown(second)
    assert first.query_count == len(QUERIES) and first.memory_count == len(MEMORIES)
    for variant in first.variants:
        assert set(variant.per_query) == {q.id for q in QUERIES}
        for attribute in ("recall", "mrr", "ndcg"):
            assert 0.0 <= variant.mean_of(attribute) <= 1.0
    assert len(first.grid) == 25


async def test_report_states_its_limits_up_front() -> None:
    markdown = render_markdown(await evaluate())
    for phrase in ("Small and synthetic", "Direction, not significance", "Not a release gate"):
        assert phrase in markdown
    assert markdown.index("Read this first") < markdown.index("## Overall")
