"""Facade-path stable failure mapping probes (R1 §4)."""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from gateway_compute import (
    CanonicalValueError,
    ComputeRequestError,
    canonical_row_hashes_v1,
)

from test_component_support import (
    assert_failure_envelope,
    empty_reader,
    minimal_request_jcs,
)


def test_contract_version_unsupported_maps_through_facade() -> None:
    request_jcs = json.dumps(
        {
            "request_schema_version": 1,
            "contract_binding": {"contract_id": "x", "semantic_version": "1.0.0"},
            "canonical_encoding_version": 1,
            "arrow_mapping_schema_version": 1,
            "declared_table_schema": {"fields": []},
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, empty_reader())
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="COMPUTE_CONTRACT_VERSION_UNSUPPORTED",
    )


def test_canonical_version_unsupported_maps_through_facade() -> None:
    request_jcs = minimal_request_jcs("[]", canonical_encoding_version=2)
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, empty_reader())
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="COMPUTE_CANONICAL_VERSION_UNSUPPORTED",
    )


def test_arrow_mapping_version_unsupported_maps_through_facade() -> None:
    request_jcs = minimal_request_jcs("[]", arrow_mapping_schema_version=2)
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, empty_reader())
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED",
    )


def test_failure_precedence_large_utf8_is_type_unsupported() -> None:
    fields = '[{"name":"s","nullable":false,"semantic_type":{"kind":"string"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array(["hello"], type=pa.large_utf8())], names=["s"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_TYPE_UNSUPPORTED",
    )


def test_failure_precedence_utf8_with_binary_declared_is_schema_mismatch() -> None:
    fields = '[{"name":"s","nullable":false,"semantic_type":{"kind":"binary"}}]'
    request_jcs = minimal_request_jcs(fields)
    batch = pa.record_batch([pa.array([b"hello"], type=pa.binary())], names=["s"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_SCHEMA_MISMATCH",
    )


def test_nan_float_maps_with_full_envelope() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"float64"}}]'
    request_jcs = minimal_request_jcs(fields)
    schema = pa.schema([pa.field("v", pa.float64(), nullable=False)])
    batch = pa.record_batch([pa.array([float("nan")], type=pa.float64())], schema=schema)
    with pytest.raises(CanonicalValueError) as exc_info:
        canonical_row_hashes_v1(request_jcs, batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=CanonicalValueError,
        expected_code="CANONICAL_VALUE_INVALID",
    )
