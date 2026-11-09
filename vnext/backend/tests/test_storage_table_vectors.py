"""A-stage storage task semantics and independent key bytes."""

from __future__ import annotations

import pytest

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.mutation_planning._digest import key_bytes_for_ordering
from gateway_backend.capabilities.mutation_planning.contracts import (
    CanonicalStorageKey,
    StorageNetCounts,
    StorageTableSummary,
)
from tests.support.storage_table_vectors import storage_table_vectors

pytestmark = pytest.mark.unit


def test_storage_key_order_uses_jcs_document_bytes() -> None:
    vectors = storage_table_vectors()
    for case in vectors["jcs_storage_keys"]:
        key = CanonicalStorageKey(
            columns=tuple(
                (entry["column"], entry["value"]) for entry in case["input_columns"]
            )
        )
        assert key_bytes_for_ordering(key) == case["expected_key_document_utf8"].encode()
    ten, two = vectors["jcs_storage_keys"][1:]
    assert ten["expected_key_document_utf8"] < two["expected_key_document_utf8"]


def test_jcs_property_order_follows_utf16_code_units() -> None:
    case = storage_table_vectors()["jcs_property_order"]
    assert canonicalize_json_value(case["input"]) == case["expected_utf8"].encode()


def test_storage_summary_keeps_unknown_diff_distinct_from_zero_diff() -> None:
    unknown = StorageTableSummary(
        before_rows=100,
        after_rows=100,
        net_counts=None,
        before_identity_validated=False,
        after_identity_validated=True,
    )
    unchanged = StorageTableSummary(
        before_rows=100,
        after_rows=100,
        net_counts=StorageNetCounts(inserted=0, updated=0, deleted=0),
        before_identity_validated=True,
        after_identity_validated=True,
    )
    assert unknown.net_counts is None
    assert unchanged.net_counts is not None and unchanged.net_counts.changed == 0
