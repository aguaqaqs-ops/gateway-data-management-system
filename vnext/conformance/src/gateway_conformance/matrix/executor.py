"""Execute required profile matrix cells."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from gateway_conformance.matrix.aggregate import (
    MatrixCellOutcome,
    MatrixSuiteOutcome,
    aggregate_matrix_outcomes,
)
from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.matrix.cells import ExecutionCell, expand_required_cells
from gateway_conformance.matrix.closure import (
    assert_exact_cell_closure,
    assert_no_duplicate_providers_in_matrix,
)
from gateway_conformance.runner.lifecycle import execute_scenario_run
from gateway_conformance.runner.registry import SubjectHarnessRegistry
from gateway_conformance.runner.runtime import LogicalClock
from gateway_conformance.scenario.discovery import discover_formal_scenarios
from gateway_conformance.scenario.validate import load_validated_scenario


def discover_formal_scenario_root() -> Path:
    roots = discover_formal_scenarios()
    if len(roots) != 1:
        raise ConformanceValidationError("expected exactly one formal scenario root")
    return roots[0]


def execute_matrix_cells(
    root: Path,
    *,
    cells: tuple[ExecutionCell, ...],
    run_id_factory: Callable[[ExecutionCell], str],
    deterministic_seed: str,
    clock: LogicalClock,
    environment_versions: list[dict[str, str]],
    registry: SubjectHarnessRegistry,
) -> tuple[MatrixCellOutcome, ...]:
    manifest, _closure = load_validated_scenario(root)
    expected = expand_required_cells(manifest)
    assert_exact_cell_closure(expected, cells)
    assert_no_duplicate_providers_in_matrix(cells)

    outcomes: list[MatrixCellOutcome] = []
    for cell in cells:
        outcome = execute_scenario_run(
            root,
            profile=cell.profile,
            provider_id=cell.provider_id,
            run_id=run_id_factory(cell),
            deterministic_seed=deterministic_seed,
            clock=clock,
            environment_versions=environment_versions,
            registry=registry,
        )
        outcomes.append(MatrixCellOutcome(cell=cell, outcome=outcome))
    return tuple(outcomes)


def execute_formal_canonical_row_hash_matrix(
    *,
    run_id_factory: Callable[[ExecutionCell], str] | None = None,
    deterministic_seed: str = "wp5-r4-matrix-seed",
    clock: LogicalClock | None = None,
    environment_versions: list[dict[str, str]],
    registry: SubjectHarnessRegistry,
) -> MatrixSuiteOutcome:
    root = discover_formal_scenario_root()
    manifest, _closure = load_validated_scenario(root)
    cells = expand_required_cells(manifest)
    if run_id_factory is None:

        def run_id_factory(cell: ExecutionCell) -> str:
            provider = cell.provider_id or "null"
            return f"wp5-r4-{cell.profile}-{provider}"

    resolved_clock = clock or LogicalClock("2026-01-01T00:00:00Z")
    cell_outcomes = execute_matrix_cells(
        root,
        cells=cells,
        run_id_factory=run_id_factory,
        deterministic_seed=deterministic_seed,
        clock=resolved_clock,
        environment_versions=environment_versions,
        registry=registry,
    )
    return aggregate_matrix_outcomes(cell_outcomes)
