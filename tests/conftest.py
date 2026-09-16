from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark anything under tests/integration/ so `-m integration` selects it
    without every test file needing to repeat the marker.

    Explicitly skips anything already marked `integration_external` (real
    Voyage/Anthropic API calls, real money per run, ADR 0009/NFR6) — without
    this exclusion, those tests would *also* pick up the plain `integration`
    marker just by living in this directory, and `pytest -m integration`
    (the free, Docker-only job) would silently start incurring real API
    cost. Confirmed this was happening before this fix: `-m integration`
    was collecting tests/integration/test_voyage_embedding_provider.py.
    """
    for item in items:
        if "tests/integration/" in str(item.fspath).replace(
            "\\", "/"
        ) and not item.get_closest_marker("integration_external"):
            item.add_marker(pytest.mark.integration)
