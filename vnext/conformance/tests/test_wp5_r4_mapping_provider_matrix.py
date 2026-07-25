"""WP5 R4 all-kind mapping provider matrix (python-reference vs rust-native)."""

from __future__ import annotations

import pytest

from gateway_conformance.harness.canonical_row_hashes.coverage_inventory import (
    assert_mapping_matrix_executed,
)
from gateway_conformance.harness.canonical_row_hashes.mapping_inventory import REQUIRED_CASE_IDS
from gateway_conformance.harness.canonical_row_hashes.mapping_matrix import (
    run_mapping_provider_matrix,
)


def test_mapping_provider_matrix_all_cases_python_vs_rust() -> None:
    executed = run_mapping_provider_matrix()
    assert_mapping_matrix_executed(executed)


def test_assert_mapping_matrix_executed_rejects_missing_case() -> None:
    missing = frozenset(REQUIRED_CASE_IDS) - {"mapping-null"}
    with pytest.raises(AssertionError, match="executed set mismatch"):
        assert_mapping_matrix_executed(missing)
