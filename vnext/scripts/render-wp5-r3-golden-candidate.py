#!/usr/bin/env python3
"""Offline helper: render WP5 R3 mixed-scalars golden candidate (not invoked by pytest)."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pyarrow as pa

VNEXT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = (
    VNEXT_ROOT
    / "fixtures"
    / "scenarios"
    / "data"
    / "canonical-row-hashes"
    / "mixed-scalars"
)

REQUEST_VALUE = {
    "request_schema_version": 1,
    "contract_binding": {
        "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
        "semantic_version": "1.0.0",
    },
    "canonical_encoding_version": 1,
    "arrow_mapping_schema_version": 1,
    "declared_table_schema": {
        "fields": [
            {
                "name": "z_label",
                "nullable": True,
                "semantic_type": {"kind": "string"},
            },
            {
                "name": "a_id",
                "nullable": False,
                "semantic_type": {"kind": "signed-integer", "bits": 32},
            },
            {
                "name": "m_flag",
                "nullable": True,
                "semantic_type": {"kind": "boolean"},
            },
            {
                "name": "amount",
                "nullable": False,
                "semantic_type": {"kind": "decimal", "precision": 10, "scale": 2},
            },
        ]
    },
}


def _build_batches() -> pa.RecordBatch:
    schema = pa.schema(
        [
            pa.field("z_label", pa.string(), nullable=True),
            pa.field("a_id", pa.int32(), nullable=False),
            pa.field("m_flag", pa.bool_(), nullable=True),
            pa.field("amount", pa.decimal128(10, 2), nullable=False),
        ]
    )
    z_label = pa.array(["beta", "alpha", "beta"], type=pa.string())
    a_id = pa.array([2, 1, 2], type=pa.int32())
    m_flag = pa.array([True, None, True], type=pa.bool_())
    amount = pa.array(
        [
            pa.scalar(Decimal("12.50"), type=pa.decimal128(10, 2)),
            pa.scalar(Decimal("-3.00"), type=pa.decimal128(10, 2)),
            pa.scalar(Decimal("12.50"), type=pa.decimal128(10, 2)),
        ]
    )
    return pa.record_batch([z_label, a_id, m_flag, amount], schema=schema)


def _request_jcs() -> bytes:
    from gateway_shared_kernel.jcs import canonicalize_json_value

    return canonicalize_json_value(REQUEST_VALUE)


def main() -> int:
    sys.path.insert(0, str(VNEXT_ROOT / "conformance" / "src"))
    from gateway_compute import canonical_row_hashes_v1

    batch = _build_batches()
    request_jcs = _request_jcs()
    output, result_jcs = canonical_row_hashes_v1(request_jcs, batch)
    _ = output.read_all()

    result_value = json.loads(result_jcs.decode())
    from gateway_shared_kernel import raw_blob_digest

    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, batch.schema) as writer:
        writer.write_batch(batch)
    ipc_bytes = bytes(sink.getvalue().to_pybytes())

    from gateway_conformance.owner.validate import (
        compute_golden_content_digest,
        compute_owner_content_digest,
    )

    contract_binding = {
        "owner": "canonical-row-hash-capability",
        "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
        "semantic_version": "1.0.0",
    }
    content_digest = compute_owner_content_digest(
        result_value,
        owner=str(contract_binding["owner"]),
        contract_id=str(contract_binding["contract_id"]),
        semantic_version=str(contract_binding["semantic_version"]),
        schema_id="gateway-vnext.canonical-table-result.v1",
        schema_version=1,
    )
    envelope = {
        "golden_envelope_schema_version": 1,
        "expectation_id": "row-hashes",
        "kind": "structured",
        "contract_binding": contract_binding,
        "payload_descriptor": {
            "media_type": "application/json",
            "schema_id": "gateway-vnext.canonical-table-result.v1",
            "schema_version": 1,
            "canonical_encoding_version": 1,
            "comparison_mode": "exact-canonical",
        },
        "content_digest": content_digest,
        "payload": {"storage": "inline", "value": result_value},
    }
    computed_envelope_digest = compute_golden_content_digest(envelope)
    assert computed_envelope_digest == content_digest

    print("=== result value ===")
    print(json.dumps(result_value, indent=2, sort_keys=True))
    print("=== content_digest ===")
    print(content_digest)
    print("=== ipc size / raw_sha256 ===")
    print(len(ipc_bytes), raw_blob_digest(ipc_bytes).value)
    print("=== request_jcs (canonical) ===")
    print(request_jcs.decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
