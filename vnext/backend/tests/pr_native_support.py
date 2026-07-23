"""Shared helpers for WP4 R4 PR-NATIVE full-chain tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, Type, cast

import pyarrow as pa

from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    RetentionClass,
    build_logical_ref,
)
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    table_schema_digest_from_declared_fields,
)
from gateway_backend.compute import canonical_row_hashes_v1

CONTRACT_BINDING = {
    "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
    "semantic_version": "1.0.0",
}

FAILURE_ENVELOPES: dict[str, bytes] = {
    "COMPUTE_REQUEST_SCHEMA_INVALID": (
        b'{"code":"COMPUTE_REQUEST_SCHEMA_INVALID","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"request"}'
    ),
    "ARROW_TYPE_UNSUPPORTED": (
        b'{"code":"ARROW_TYPE_UNSUPPORTED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"schema"}'
    ),
    "ARROW_SCHEMA_MISMATCH": (
        b'{"code":"ARROW_SCHEMA_MISMATCH","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"schema"}'
    ),
    "CANONICAL_VALUE_INVALID": (
        b'{"code":"CANONICAL_VALUE_INVALID","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"canonicalize"}'
    ),
    "ARROW_STREAM_IMPORT_FAILED": (
        b'{"code":"ARROW_STREAM_IMPORT_FAILED","contract_binding":'
        b'{"contract_id":"gateway-vnext.canonical-row-hash-compute-boundary",'
        b'"semantic_version":"1.0.0"},"diagnostics":[],"effect":"NONE",'
        b'"failure_schema_version":1,"retry_class":"NEVER","stage":"arrow-import"}'
    ),
}


class _FailureEnvelope(Protocol):
    code: str
    stage: str
    envelope_jcs: bytes


def minimal_request_jcs(fields_json: str) -> bytes:
    payload = {
        "request_schema_version": 1,
        "contract_binding": CONTRACT_BINDING,
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": json.loads(fields_json)},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def run_full_chain(
    store: ArtifactStorePort,
    *,
    fields: list[dict[str, object]],
    data: pa.Table | pa.RecordBatch | pa.RecordBatchReader,
    logical_ref: str,
    retention_class: RetentionClass = RetentionClass.OPERATION,
) -> tuple[ArtifactRef, CanonicalRowHashesArtifactManifest, bytes]:
    """Execute facade -> compute -> persist -> reopen on the given store."""

    fields_json = json.dumps(fields)
    output, result_jcs = canonical_row_hashes_v1(minimal_request_jcs(fields_json), data)
    content = content_manifest_from_compute_result(result_jcs)
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
        retention_class=retention_class,
    )
    reopen_and_verify_canonical_row_hash_artifact(
        store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )
    return ref, content, result_jcs


def assert_failure_envelope(
    exc: BaseException,
    *,
    expected_type: Type[BaseException],
    expected_code: str,
) -> None:
    assert isinstance(exc, expected_type), type(exc)
    failure = cast(_FailureEnvelope, exc)
    assert failure.code == expected_code
    golden = json.loads(FAILURE_ENVELOPES[expected_code].decode())
    assert failure.stage == golden["stage"]
    envelope = failure.envelope_jcs
    assert envelope, "envelope_jcs must be non-empty"
    assert envelope == FAILURE_ENVELOPES[expected_code]
    parsed = json.loads(envelope.decode())
    assert parsed == golden
    assert parsed["effect"] == "NONE"
    assert parsed["failure_schema_version"] == 1
    assert parsed["diagnostics"] == []


def assert_independent_table_schema_digest_oracle(
    fields: list[dict[str, object]],
    result_jcs: bytes,
) -> None:
    """Cross-check compute result digest with an independent oracle."""

    payload = json.loads(result_jcs)
    recomputed = table_schema_digest_from_declared_fields(fields)
    assert recomputed.value == payload["table_schema_digest"]


def count_reader_batches(reader: pa.RecordBatchReader) -> int:
    """Count batches in a RecordBatchReader without materializing rows."""

    count = 0
    for _batch in reader:
        count += 1
    return count


def assert_multi_batch_input(data: pa.RecordBatchReader) -> None:
    assert count_reader_batches(data) >= 2


def count_ipc_record_batches(raw_bytes: bytes) -> int:
    """Count Arrow IPC record batches using an independent framing reader."""

    buffer_reader = pa.BufferReader(raw_bytes)
    reader = pa.ipc.open_stream(buffer_reader)
    count = 0
    while True:
        try:
            reader.read_next_batch()
            count += 1
        except StopIteration:
            break
    return count


def assert_ref_json_has_no_host_paths(ref: ArtifactRef) -> None:
    from gateway_backend.artifacts import artifact_ref_to_json

    serialized = artifact_ref_to_json(ref)
    forbidden_prefixes = ("/tmp/", "/var/", "file:", "\\\\")
    for marker in forbidden_prefixes:
        assert marker not in serialized, serialized
    assert "\\" not in serialized, serialized


def assert_public_boundary_sanitized(
    exc: BaseException,
    *,
    forbidden_path: Path | None = None,
) -> None:
    """Fail closed when public errors leak host paths or traceback fragments."""

    message = str(exc)
    forbidden_markers: tuple[str, ...] = (
        "/tmp/",
        "/var/",
        "Traceback (most recent call last)",
        'File "',
    )
    if forbidden_path is not None:
        forbidden_markers = forbidden_markers + (str(forbidden_path),)
    for marker in forbidden_markers:
        assert marker not in message, message


def build_logical_ref_for_case(case_id: str) -> str:
    return build_logical_ref("canonical-row-hash", case_id)


class BytesOnlyArtifactStore:
    """Returns fixed bytes without envelope identity checks (reopen envelope tests)."""

    def __init__(self, raw_bytes: bytes) -> None:
        self._raw_bytes = raw_bytes

    def locate(self, ref: ArtifactRef) -> bytes:
        _ = ref
        return self._raw_bytes

    def put(self, raw_bytes: bytes, manifest: object) -> ArtifactRef:
        raise NotImplementedError

    def verify_manifest(self, manifest: object) -> None:
        _ = manifest
