from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rootmem.consolidation.trigger import TriggerSettings, should_consolidate
from rootmem.storage.consolidation_protocols import ConsolidationRun

_SETTINGS = TriggerSettings(episode_threshold=500, time_window_hours=24.0)
_NOW = datetime(2026, 1, 2, tzinfo=UTC)


def _run(started_at: datetime) -> ConsolidationRun:
    return ConsolidationRun(
        id="run-1", namespace="ns", trigger_reason="time", started_at=started_at
    )


class TestShouldConsolidate:
    def test_force_bypasses_every_other_check(self) -> None:
        decision = should_consolidate(
            unconsolidated_count=0, last_run=_run(_NOW), now=_NOW, settings=_SETTINGS, force=True
        )
        assert decision.should_run is True
        assert decision.trigger_reason == "manual"

    def test_count_threshold_crossed_triggers(self) -> None:
        decision = should_consolidate(
            unconsolidated_count=500, last_run=_run(_NOW), now=_NOW, settings=_SETTINGS
        )
        assert decision.should_run is True
        assert decision.trigger_reason == "count"

    def test_count_below_threshold_does_not_trigger_alone(self) -> None:
        decision = should_consolidate(
            unconsolidated_count=499, last_run=_run(_NOW), now=_NOW, settings=_SETTINGS
        )
        assert decision.should_run is False

    def test_no_prior_run_always_triggers(self) -> None:
        decision = should_consolidate(
            unconsolidated_count=0, last_run=None, now=_NOW, settings=_SETTINGS
        )
        assert decision.should_run is True
        assert decision.trigger_reason == "time"

    def test_time_window_elapsed_triggers(self) -> None:
        last_run = _run(_NOW - timedelta(hours=25))
        decision = should_consolidate(
            unconsolidated_count=0, last_run=last_run, now=_NOW, settings=_SETTINGS
        )
        assert decision.should_run is True
        assert decision.trigger_reason == "time"

    def test_time_window_not_elapsed_does_not_trigger(self) -> None:
        last_run = _run(_NOW - timedelta(hours=1))
        decision = should_consolidate(
            unconsolidated_count=0, last_run=last_run, now=_NOW, settings=_SETTINGS
        )
        assert decision.should_run is False
        assert decision.trigger_reason is None
