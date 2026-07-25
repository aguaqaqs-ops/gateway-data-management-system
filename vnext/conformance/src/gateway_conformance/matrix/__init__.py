"""Required profile matrix planner and executor."""

from __future__ import annotations

from gateway_conformance.matrix.aggregate import (
    MatrixCellOutcome,
    MatrixSuiteOutcome,
    aggregate_matrix_outcomes,
    suite_summary_wire,
)
from gateway_conformance.matrix.cells import ExecutionCell, expand_required_cells
from gateway_conformance.matrix.closure import (
    assert_cell_legality,
    assert_exact_cell_closure,
    assert_no_duplicate_providers_in_matrix,
)
from gateway_conformance.matrix.executor import (
    execute_formal_canonical_row_hash_matrix,
    execute_matrix_cells,
)
from gateway_conformance.matrix.identity import matrix_semantic_fingerprint

__all__ = [
    "ExecutionCell",
    "MatrixCellOutcome",
    "MatrixSuiteOutcome",
    "aggregate_matrix_outcomes",
    "assert_cell_legality",
    "assert_exact_cell_closure",
    "assert_no_duplicate_providers_in_matrix",
    "execute_formal_canonical_row_hash_matrix",
    "execute_matrix_cells",
    "expand_required_cells",
    "matrix_semantic_fingerprint",
    "suite_summary_wire",
]
