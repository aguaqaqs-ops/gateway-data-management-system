"""Executed-set guard for all-kind mapping provider matrix."""

from __future__ import annotations

from gateway_conformance.harness.canonical_row_hashes.mapping_inventory import (
    REQUIRED_CASE_IDS,
    kinds_covered_by,
    iter_required_cases,
)
from gateway_shared_kernel import DeclaredTypeKind

CANONICAL_SEMANTIC_KINDS: frozenset[str] = frozenset(kind.value for kind in DeclaredTypeKind)


def assert_mapping_matrix_executed(executed_case_ids: frozenset[str]) -> None:
    if executed_case_ids != REQUIRED_CASE_IDS:
        missing = sorted(REQUIRED_CASE_IDS - executed_case_ids)
        extra = sorted(executed_case_ids - REQUIRED_CASE_IDS)
        raise AssertionError(
            f"mapping matrix executed set mismatch missing={missing!r} extra={extra!r}"
        )
    kinds = kinds_covered_by(iter_required_cases())
    if kinds != CANONICAL_SEMANTIC_KINDS:
        missing_kinds = sorted(CANONICAL_SEMANTIC_KINDS - kinds)
        raise AssertionError(f"mapping inventory missing kinds: {missing_kinds!r}")
