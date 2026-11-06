"""Default test classification for Backend unit tests."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Iterator

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


@pytest.fixture(scope="session", autouse=True)
def initialize_kernel_pool() -> None:
    from gateway_compute._native import _init_kernel_native

    _init_kernel_native(1)


@pytest.fixture(autouse=True)
def operation_kernel_context() -> Iterator[None]:
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, kernel_execution_scope, NeverCancel,
    )

    with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(8 * 1024**3), NeverCancel(), 1)):
        yield
