"""WP4 R4 PR-NATIVE artifact/data-path full-chain success matrix."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa

from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_to_json
from gateway_backend.canonical_row_hash_ipc import (
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    reopen_and_verify_canonical_row_hash_artifact,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore

from pr_native_support import (
    assert_independent_table_schema_digest_oracle,
    assert_multi_batch_input,
    assert_ref_json_has_no_host_paths,
    build_logical_ref_for_case,
    count_ipc_record_batches,
    minimal_request_jcs,
    run_full_chain,
)

pytestmark = __import__("pytest").mark.pr_native


def test_row_permutation_preserves_semantic_identity_full_chain() -> None:
    fields = [
        {"name": "a", "nullable": False, "semantic_type": {"kind": "signed-integer", "bits": 32}},
        {"name": "b", "nullable": False, "semantic_type": {"kind": "signed-integer", "bits": 32}},
    ]
    schema = pa.schema(
        [
            pa.field("a", pa.int32(), nullable=False),
            pa.field("b", pa.int32(), nullable=False),
        ]
    )
    batch_a = pa.record_batch(
        [pa.array([1, 2], type=pa.int32()), pa.array([10, 20], type=pa.int32())],
        schema=schema,
    )
    batch_b = pa.record_batch(
        [pa.array([2, 1], type=pa.int32()), pa.array([20, 10], type=pa.int32())],
        schema=schema,
    )
    store = InMemoryArtifactStore()
    _, content_a, result_a = run_full_chain(
        store,
        fields=fields,
        data=batch_a,
        logical_ref=build_logical_ref_for_case("row-perm-a"),
    )
    _, content_b, result_b = run_full_chain(
        store,
        fields=fields,
        data=batch_b,
        logical_ref=build_logical_ref_for_case("row-perm-b"),
    )
    assert result_a == result_b
    assert content_a.raw_content_digest == content_b.raw_content_digest
    assert_independent_table_schema_digest_oracle(fields, result_a)


def test_field_permutation_preserves_semantic_identity_full_chain() -> None:
    fields = [
        {"name": "a", "nullable": False, "semantic_type": {"kind": "string"}},
        {"name": "b", "nullable": False, "semantic_type": {"kind": "string"}},
    ]
    schema = pa.schema(
        [
            pa.field("a", pa.string(), nullable=False),
            pa.field("b", pa.string(), nullable=False),
        ]
    )
    batch = pa.record_batch(
        [pa.array(["x"], type=pa.string()), pa.array(["y"], type=pa.string())],
        schema=schema,
    )
    permuted = batch.select(["b", "a"])
    store = InMemoryArtifactStore()
    _, content_a, result_a = run_full_chain(
        store,
        fields=fields,
        data=batch,
        logical_ref=build_logical_ref_for_case("field-perm-a"),
    )
    _, content_b, result_b = run_full_chain(
        store,
        fields=fields,
        data=permuted,
        logical_ref=build_logical_ref_for_case("field-perm-b"),
    )
    assert result_a == result_b
    assert content_a.raw_content_digest == content_b.raw_content_digest


def test_fresh_local_store_instance_reopen_full_chain(tmp_path: Path) -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True, False]}),
        logical_ref=build_logical_ref_for_case("fresh-reopen"),
    )
    fresh_store = LocalArtifactStore(artifact_root)
    reopen_and_verify_canonical_row_hash_artifact(
        fresh_store,
        ref,
        expected_content=content,
        declared_table_schema_fields=fields,
    )
    assert_ref_json_has_no_host_paths(ref)


def test_multi_batch_input_full_chain_preserves_semantic_identity() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False, False])], names=["flag"])
    multi_input = pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b])
    assert_multi_batch_input(multi_input)
    store = InMemoryArtifactStore()
    ref, _, _ = run_full_chain(
        store,
        fields=fields,
        data=multi_input,
        logical_ref=build_logical_ref_for_case("multi-batch-input"),
    )
    raw_bytes = store.locate(ref)
    assert count_ipc_record_batches(raw_bytes) >= 1


def test_nullable_string_smoke_full_chain() -> None:
    fields = [{"name": "label", "nullable": True, "semantic_type": {"kind": "string"}}]
    schema = pa.schema([pa.field("label", pa.string(), nullable=True)])
    batch = pa.record_batch(
        [pa.array(["alpha", None, "beta"], type=pa.string())],
        schema=schema,
    )
    store = InMemoryArtifactStore()
    ref, content, result_jcs = run_full_chain(
        store,
        fields=fields,
        data=batch,
        logical_ref=build_logical_ref_for_case("nullable-string"),
    )
    assert_independent_table_schema_digest_oracle(fields, result_jcs)
    assert_ref_json_has_no_host_paths(ref)
    reopened_hashes = collect_row_hashes_from_ipc(store.locate(ref))
    assert len(reopened_hashes) == 3
    assert content.row_count == "3"


def test_artifact_ref_json_is_location_independent(tmp_path: Path) -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    logical_ref = build_logical_ref_for_case("stable-ref")
    store_a = LocalArtifactStore(tmp_path / "root-a")
    store_b = LocalArtifactStore(tmp_path / "root-b")
    ref_a, _, _ = run_full_chain(
        store_a,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=logical_ref,
    )
    ref_b, _, _ = run_full_chain(
        store_b,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=logical_ref,
    )
    serialized_a = artifact_ref_to_json(ref_a)
    serialized_b = artifact_ref_to_json(ref_b)
    assert serialized_a == serialized_b
    assert "/tmp" not in serialized_a
    assert str(tmp_path) not in serialized_a


def test_batch_partition_change_preserves_semantic_digest_full_chain() -> None:
    fields = [{"name": "flag", "nullable": True, "semantic_type": {"kind": "boolean"}}]
    single_output, single_result = canonical_row_hashes_v1(
        minimal_request_jcs(json.dumps(fields)),
        pa.table({"flag": [True, False]}),
    )
    single_content = content_manifest_from_compute_result(single_result)
    batch_a = pa.record_batch([pa.array([True])], names=["flag"])
    batch_b = pa.record_batch([pa.array([False])], names=["flag"])
    store = InMemoryArtifactStore()
    _, multi_content, _ = run_full_chain(
        store,
        fields=fields,
        data=pa.RecordBatchReader.from_batches(batch_a.schema, [batch_a, batch_b]),
        logical_ref=build_logical_ref_for_case("partition-change"),
    )
    assert single_content.raw_content_digest == multi_content.raw_content_digest
    assert single_content.table_schema_digest == multi_content.table_schema_digest
