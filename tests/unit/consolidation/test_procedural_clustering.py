from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootmem.consolidation.procedural_clustering import build_trace_pairs, group_session_traces
from rootmem.storage.models import MemoryRecord

_BASE_TIME = datetime(2026, 9, 18, tzinfo=UTC)


def _episode(
    *,
    id: str,
    content: str,
    session_id: str | None,
    outcome: str | None,
    offset_seconds: int,
) -> MemoryRecord:
    return MemoryRecord(
        id=id,
        namespace="ns",
        content=content,
        source="test",
        source_session_id=session_id,
        session_outcome=outcome,
        created_at=_BASE_TIME + timedelta(seconds=offset_seconds),
        updated_at=_BASE_TIME + timedelta(seconds=offset_seconds),
    )


class TestGroupSessionTraces:
    def test_groups_episodes_sharing_session_id_and_outcome(self) -> None:
        episodes = [
            _episode(
                id="1", content="step one", session_id="s1", outcome="success", offset_seconds=0
            ),
            _episode(
                id="2", content="step two", session_id="s1", outcome="success", offset_seconds=1
            ),
        ]

        traces = group_session_traces(episodes, min_session_length=2)

        assert len(traces) == 1
        assert traces[0].session_id == "s1"
        assert traces[0].outcome == "success"
        assert traces[0].memory_ids == ["1", "2"]

    def test_orders_by_created_at_not_input_order(self) -> None:
        episodes = [
            _episode(
                id="2", content="second", session_id="s1", outcome="success", offset_seconds=5
            ),
            _episode(id="1", content="first", session_id="s1", outcome="success", offset_seconds=0),
        ]

        traces = group_session_traces(episodes, min_session_length=2)

        assert traces[0].memory_ids == ["1", "2"]
        assert traces[0].summary_text == "first\nsecond"

    def test_excludes_episodes_with_no_session_id(self) -> None:
        episodes = [
            _episode(id="1", content="a", session_id=None, outcome="success", offset_seconds=0),
            _episode(id="2", content="b", session_id=None, outcome="success", offset_seconds=1),
        ]

        assert group_session_traces(episodes, min_session_length=2) == []

    def test_excludes_episodes_with_no_outcome(self) -> None:
        episodes = [
            _episode(id="1", content="a", session_id="s1", outcome=None, offset_seconds=0),
            _episode(id="2", content="b", session_id="s1", outcome=None, offset_seconds=1),
        ]

        assert group_session_traces(episodes, min_session_length=2) == []

    def test_drops_sessions_below_min_length(self) -> None:
        episodes = [
            _episode(
                id="1", content="only step", session_id="s1", outcome="success", offset_seconds=0
            ),
        ]

        assert group_session_traces(episodes, min_session_length=2) == []

    def test_separates_different_sessions(self) -> None:
        episodes = [
            _episode(id="1", content="a1", session_id="s1", outcome="success", offset_seconds=0),
            _episode(id="2", content="a2", session_id="s1", outcome="success", offset_seconds=1),
            _episode(id="3", content="b1", session_id="s2", outcome="failure", offset_seconds=0),
            _episode(id="4", content="b2", session_id="s2", outcome="failure", offset_seconds=1),
        ]

        traces = group_session_traces(episodes, min_session_length=2)

        assert {t.session_id for t in traces} == {"s1", "s2"}
        assert {t.outcome for t in traces} == {"success", "failure"}

    def test_same_session_id_different_outcome_are_separate_groups(self) -> None:
        """A session id is only meaningfully a trace in combination with its
        outcome -- this shouldn't normally happen in practice (one session
        has one outcome), but the grouping key must not silently merge rows
        that disagree on outcome."""
        episodes = [
            _episode(id="1", content="a", session_id="s1", outcome="success", offset_seconds=0),
            _episode(id="2", content="b", session_id="s1", outcome="failure", offset_seconds=1),
        ]

        traces = group_session_traces(episodes, min_session_length=1)

        assert len(traces) == 2


class TestBuildTracePairs:
    def test_builds_a_pair_per_combination(self) -> None:
        pairs = build_trace_pairs({"a": [1.0, 0.0], "b": [1.0, 0.0], "c": [0.0, 1.0]})

        as_dict = {frozenset((x, y)): sim for x, y, sim in pairs}
        assert as_dict[frozenset(("a", "b"))] == 1.0
        assert as_dict[frozenset(("a", "c"))] == 0.0

    def test_empty_input_gives_no_pairs(self) -> None:
        assert build_trace_pairs({}) == []

    def test_single_trace_gives_no_pairs(self) -> None:
        assert build_trace_pairs({"a": [1.0, 0.0]}) == []
