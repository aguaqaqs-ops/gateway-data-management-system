"""Default test classification for Backend unit tests."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if (
            item.get_closest_marker("integration") is None
            and item.get_closest_marker("serial") is None
            and item.get_closest_marker("unit") is None
        ):
            item.add_marker(pytest.mark.unit)
