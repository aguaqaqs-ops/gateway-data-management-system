"""End-to-end canonical row-hash artifact round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pytest

from gateway_backend.artifacts import (
    InMemoryArtifactStore,
    RetentionClass,
    artifact_ref_to_json,
    build_logical_ref,
)
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    CanonicalRowHashIpcError,
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    table_schema_digest_from_declared_fields,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
from gateway_shared_kernel import DigestRef

pytestmark = pytest.mark.pr_native


def minimal_request_jcs(fields_json: str) -> bytes:
    payload = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": json.loads(fields_json)},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _run_compute(
    fields_json: str, data: pa.Table | pa.RecordBatch | pa.RecordBatchReader
) -> tuple[pa.RecordBatchReader, bytes]:
    return canonical_row_hashes_v1(minimal_request_jcs(fields_json), data)


@pytest.mark.parametrize(
    ("fields_json", "data"),
    [
        ("[]", pa.table({})),
        (
            '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]',
            pa.table({"flag": [True]}),
        ),
        (
            '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]',
            pa.table({"flag": [True, True, False]}),
        ),
    ],
)
def test_in_memory_round_trip(fields_json: str, data: pa.Table) -> None:
    fields = json.loads(fields_json)
    output, result_jcs = _run_compute(fields_json, data)
    content = content_manifest_from_compute_result(result_jcs)
    store = InMemoryArtifactStore()
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "roundtrip-case"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
        retention_class=RetentionClass.OPERATION,
    )
    reopen_and_verify_canonical_row_hash_artifact(
        store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )


def test_local_store_round_trip(tmp_path: Path) -> None:
    fields_json = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    fields = json.loads(fields_json)
    output, result_jcs = _run_compute(fields_json, pa.table({"flag": [False, True]}))
    content = content_manifest_from_compute_result(result_jcs)
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "local-roundtrip"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    reopen_and_verify_canonical_row_hash_artifact(
        store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )


def test_different_store_roots_do_not_change_serialized_ref(tmp_path: Path) -> None:
    fields_json = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    fields = json.loads(fields_json)
    output, result_jcs = _run_compute(fields_json, pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    logical_ref = build_logical_ref("canonical-row-hash", "stable-ref")
    store_a = LocalArtifactStore(tmp_path / "root-a")
    store_b = LocalArtifactStore(tmp_path / "root-b")
    ref_a = persist_canonical_row_hash_stream(
        store_a,
        logical_ref=logical_ref,
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    output_b, _ = _run_compute(fields_json, pa.table({"flag": [True]}))
    ref_b = persist_canonical_row_hash_stream(
        store_b,
        logical_ref=logical_ref,
        reader=output_b,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    assert artifact_ref_to_json(ref_a) == artifact_ref_to_json(ref_b)


def test_semantic_identity_stable_across_chunking() -> None:
    fields_json = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    single_output, single_result = _run_compute(fields_json, pa.table({"flag": [True, False]}))
    single_content = content_manifest_from_compute_result(single_result)
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False])], names=["flag"])
    multi_output, multi_result = _run_compute(
        fields_json,
        pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b]),
    )
    multi_content = content_manifest_from_compute_result(multi_result)
    assert single_content.raw_content_digest.value == multi_content.raw_content_digest.value
    assert single_content.table_schema_digest.value == multi_content.table_schema_digest.value


def test_table_schema_digest_matches_compute_result() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    _, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    payload = json.loads(result_jcs)
    recomputed = table_schema_digest_from_declared_fields(fields)
    assert recomputed.value == payload["table_schema_digest"]


def test_duplicate_row_hashes_round_trip() -> None:
    fields_json = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    fields = json.loads(fields_json)
    output, result_jcs = _run_compute(fields_json, pa.table({"flag": [True, True]}))
    content = content_manifest_from_compute_result(result_jcs)
    store = InMemoryArtifactStore()
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "duplicate-roundtrip"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    reopen_and_verify_canonical_row_hash_artifact(
        store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )


def test_multi_batch_round_trip() -> None:
    fields_json = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    fields = json.loads(fields_json)
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False])], names=["flag"])
    output, result_jcs = _run_compute(
        fields_json,
        pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b]),
    )
    content = content_manifest_from_compute_result(result_jcs)
    store = InMemoryArtifactStore()
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "multi-batch-roundtrip"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    raw_bytes = store.locate(ref)
    reopened_hashes = collect_row_hashes_from_ipc(raw_bytes)
    single_batch_output, _ = _run_compute(fields_json, pa.table({"flag": [True, False]}))
    single_hashes = collect_row_hashes_from_ipc(write_row_hash_ipc_stream(single_batch_output))
    assert reopened_hashes == single_hashes
    reopen_and_verify_canonical_row_hash_artifact(
        store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )


def test_forged_table_schema_digest_reopen_fails() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    forged = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=DigestRef("sha256:" + "f" * 64),
        row_count=content.row_count,
    )
    store = InMemoryArtifactStore()
    ref = persist_canonical_row_hash_stream(
        store,
        logical_ref=build_logical_ref("canonical-row-hash", "forged-schema"),
        reader=output,
        content_manifest=content,
        declared_table_schema_fields=fields,
    )
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=forged,
            declared_table_schema_fields=fields,
        )


def test_publish_rejects_row_count_mismatch_before_ref() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="999",
    )
    store = InMemoryArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="row_count mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref("canonical-row-hash", "bad-row-count"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )
