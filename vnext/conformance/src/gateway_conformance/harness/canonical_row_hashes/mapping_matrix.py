"""Dual-provider mapping matrix: python-reference vs rust-native per inventory case."""

from __future__ import annotations

import io
import json

import pyarrow as pa
from gateway_shared_kernel import canonicalize_jcs

from gateway_conformance.harness.canonical_row_hashes.mapping_inventory import (
    MappingCase,
    iter_required_cases,
)
from gateway_conformance.owner.arrow_row_hash_oracle import compute_table_content_identity
from gateway_conformance.owner.canonical_row_hash import table_schema_digest_from_declared_fields

_CONTRACT_BINDING = {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0",
}


def request_jcs_for_case(case: MappingCase) -> bytes:
    fields = [dict(item) for item in case.declared_fields]
    payload = {
        "request_schema_version": 1,
        "contract_binding": _CONTRACT_BINDING,
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": fields},
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return canonicalize_jcs(encoded)


def _reference_quadruple(case: MappingCase) -> tuple[str, str, str, list[bytes]]:
    fields = [dict(item) for item in case.declared_fields]
    row_count, raw_content_digest, sorted_hashes = compute_table_content_identity(
        case.ipc_bytes, fields
    )
    table_schema_digest = table_schema_digest_from_declared_fields(fields)
    return table_schema_digest, row_count, raw_content_digest, sorted_hashes


def _native_quadruple(case: MappingCase) -> tuple[str, str, str, list[bytes]]:
    from gateway_backend.canonical_row_hash_ipc import (
        collect_row_hashes_from_ipc,
        write_row_hash_ipc_stream,
    )
    from gateway_backend.compute import canonical_row_hashes_v1

    request_jcs = request_jcs_for_case(case)
    reader = pa.ipc.open_stream(io.BytesIO(case.ipc_bytes))
    output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
    canonical = canonicalize_jcs(result_jcs)
    payload = json.loads(canonical)
    if not isinstance(payload, dict):
        raise AssertionError("rust-native result must be object")
    table_schema_digest = str(payload["table_schema_digest"])
    row_count = str(payload["row_count"])
    raw_content_digest = str(payload["raw_content_digest"])
    ipc_out = write_row_hash_ipc_stream(output)
    sorted_hashes = collect_row_hashes_from_ipc(ipc_out)
    return table_schema_digest, row_count, raw_content_digest, sorted_hashes


def _assert_quadruple_equal(
    case_id: str,
    reference: tuple[str, str, str, list[bytes]],
    native: tuple[str, str, str, list[bytes]],
) -> None:
    ref_schema, ref_count, ref_digest, ref_hashes = reference
    nat_schema, nat_count, nat_digest, nat_hashes = native
    if ref_schema != nat_schema:
        raise AssertionError(f"{case_id}: table_schema_digest mismatch")
    if ref_count != nat_count:
        raise AssertionError(f"{case_id}: row_count mismatch")
    if ref_digest != nat_digest:
        raise AssertionError(f"{case_id}: raw_content_digest mismatch")
    if ref_hashes != nat_hashes:
        raise AssertionError(f"{case_id}: sorted row hashes mismatch")


def run_mapping_provider_matrix() -> frozenset[str]:
    executed: list[str] = []
    for case in iter_required_cases():
        reference = _reference_quadruple(case)
        native = _native_quadruple(case)
        _assert_quadruple_equal(case.case_id, reference, native)
        executed.append(case.case_id)
    return frozenset(executed)
