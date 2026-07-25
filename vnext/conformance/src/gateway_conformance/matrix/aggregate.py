"""Suite-level matrix result aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway_conformance.runner.lifecycle import RunOutcome
from gateway_conformance.matrix.cells import ExecutionCell


@dataclass(frozen=True, slots=True)
class MatrixCellOutcome:
    cell: ExecutionCell
    outcome: RunOutcome


@dataclass(frozen=True, slots=True)
class MatrixSuiteOutcome:
    passed: bool
    cells: tuple[MatrixCellOutcome, ...]
    failure_reasons: tuple[str, ...]


def aggregate_matrix_outcomes(cells: tuple[MatrixCellOutcome, ...]) -> MatrixSuiteOutcome:
    reasons: list[str] = []
    passed = True
    for item in cells:
        result = item.outcome.result
        status = str(result.get("status", ""))
        cleanup = result.get("cleanup")
        cleanup_status = ""
        if isinstance(cleanup, dict):
            cleanup_status = str(cleanup.get("status", ""))
        if status != "PASSED":
            passed = False
            reasons.append(f"{item.cell.profile}/{item.cell.provider_id}: status={status}")
        elif cleanup_status != "CLEAN":
            passed = False
            reasons.append(f"{item.cell.profile}/{item.cell.provider_id}: cleanup={cleanup_status}")
    return MatrixSuiteOutcome(passed=passed, cells=cells, failure_reasons=tuple(reasons))


def suite_summary_wire(cells: tuple[MatrixCellOutcome, ...]) -> dict[str, Any]:
    wire_cells: list[dict[str, Any]] = []
    for item in sorted(cells, key=lambda c: c.cell.execution_key_tuple()):
        result = item.outcome.result
        execution_key = result.get("execution_key", {})
        wire_cells.append(
            {
                "profile": str(execution_key.get("profile", item.cell.profile)),
                "provider_id": execution_key.get("provider_id", item.cell.provider_id),
                "status": str(result.get("status", "")),
                "comparison_outcome": str(result.get("comparison_outcome", "")),
                "cleanup_status": str(
                    (result.get("cleanup") or {}).get("status", "")
                    if isinstance(result.get("cleanup"), dict)
                    else ""
                ),
            }
        )
    aggregate = aggregate_matrix_outcomes(cells)
    return {
        "matrix_suite_schema_version": 1,
        "passed": aggregate.passed,
        "cells": wire_cells,
        "failure_reasons": list(aggregate.failure_reasons),
    }
