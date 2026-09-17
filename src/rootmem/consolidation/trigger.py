"""The consolidation trigger (ADR 0012/0016). Pure function, zero I/O — the
inputs (`unconsolidated_count`, `last_run`) are fetched by
`consolidation.distill`'s orchestration via `MemoryRepository`/
`ConsolidationRepository`, not here.

Full derivation: docs/math-spec/phase2-math-spec.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from rootmem.config import Settings
    from rootmem.storage.consolidation_protocols import ConsolidationRun


@dataclass(frozen=True)
class TriggerSettings:
    episode_threshold: int
    time_window_hours: float

    @classmethod
    def from_settings(cls, settings: Settings) -> TriggerSettings:
        return cls(
            episode_threshold=settings.consolidation_episode_threshold,
            time_window_hours=settings.consolidation_time_window_hours,
        )


@dataclass(frozen=True)
class ConsolidationDecision:
    should_run: bool
    trigger_reason: Literal["count", "time", "manual"] | None


def should_consolidate(
    *,
    unconsolidated_count: int,
    last_run: ConsolidationRun | None,
    now: datetime,
    settings: TriggerSettings,
    force: bool = False,
) -> ConsolidationDecision:
    if force:
        return ConsolidationDecision(should_run=True, trigger_reason="manual")
    if unconsolidated_count >= settings.episode_threshold:
        return ConsolidationDecision(should_run=True, trigger_reason="count")
    if last_run is None:
        # No prior run for this namespace -- always eligible for the
        # time-based trigger, since "time since last run" is otherwise
        # undefined.
        return ConsolidationDecision(should_run=True, trigger_reason="time")
    hours_since_last_run = (now - last_run.started_at).total_seconds() / 3600
    if hours_since_last_run >= settings.time_window_hours:
        return ConsolidationDecision(should_run=True, trigger_reason="time")
    return ConsolidationDecision(should_run=False, trigger_reason=None)
