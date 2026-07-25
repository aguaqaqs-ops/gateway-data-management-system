"""Matrix cell closure validation."""

from __future__ import annotations

from collections.abc import Iterable

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.constants import (
    FORMAL_PROVIDER_MATRIX_PROVIDER_IDS,
)
from gateway_conformance.matrix.cells import ExecutionCell


def assert_cell_legality(cell: ExecutionCell) -> None:
    if cell.profile in {"reference", "integration"}:
        if cell.provider_id is not None:
            raise ConformanceValidationError(f"{cell.profile} profile requires null provider_id")
    elif cell.profile == "provider-matrix":
        if cell.provider_id is None:
            raise ConformanceValidationError("provider-matrix requires non-null provider_id")
        if cell.provider_id not in FORMAL_PROVIDER_MATRIX_PROVIDER_IDS:
            raise ConformanceValidationError(f"unknown provider_id: {cell.provider_id}")
    else:
        raise ConformanceValidationError(f"unknown profile: {cell.profile}")


def assert_exact_cell_closure(
    expected: tuple[ExecutionCell, ...],
    executed: Iterable[ExecutionCell],
) -> None:
    executed_list = list(executed)
    for cell in executed_list:
        assert_cell_legality(cell)
    if len(executed_list) != len(set(executed_list)):
        raise ConformanceValidationError("duplicate matrix cells in execution plan")
    if len(executed_list) != len(expected):
        raise ConformanceValidationError(
            f"matrix cell count mismatch: expected {len(expected)}, got {len(executed_list)}"
        )
    expected_set = set(expected)
    executed_set = set(executed_list)
    if executed_set != expected_set:
        missing = expected_set - executed_set
        extra = executed_set - expected_set
        raise ConformanceValidationError(
            f"matrix cell closure mismatch missing={missing!r} extra={extra!r}"
        )
    if len(executed_list) != len(executed_set):
        raise ConformanceValidationError("duplicate matrix cells in execution plan")


def assert_no_duplicate_providers_in_matrix(cells: tuple[ExecutionCell, ...]) -> None:
    seen: set[tuple[str, str | None]] = set()
    for cell in cells:
        key = cell.execution_key_tuple()
        if key in seen:
            raise ConformanceValidationError(f"duplicate matrix cell: {key}")
        seen.add(key)
