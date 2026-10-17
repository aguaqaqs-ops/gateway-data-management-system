"""Default test classification for Backend unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.dolt import dolt_available


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    from gateway_backend.infrastructure.control_db.database import initialize_control_db

    path = tmp_path / "control.sqlite3"
    initialize_control_db(path)
    return path


@pytest.fixture
def requires_dolt() -> None:
    if not dolt_available():
        pytest.skip("dolt is not available")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    for item in items:
        if (
            item.get_closest_marker("serial") is not None
            and item.get_closest_marker("parallel_safe") is None
        ):
            item.add_marker(pytest.mark.xdist_group("serial"))

        if (
            item.get_closest_marker("integration") is None
            and item.get_closest_marker("unit") is None
        ):
            item.add_marker(pytest.mark.unit)
