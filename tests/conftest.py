from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark anything under tests/integration/ so `-m integration` selects it
    without every test file needing to repeat the marker."""
    for item in items:
        if "tests/integration/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
