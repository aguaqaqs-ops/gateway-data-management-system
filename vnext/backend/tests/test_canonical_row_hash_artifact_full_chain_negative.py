"""WP4 R4 PR-NATIVE artifact/data-path full-chain failure and effect matrix."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pyarrow as pa
import pytest

from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    RetentionClass,
    put_with_built_manifest,
)
from gateway_backend.artifacts.serialize import build_manifest
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.canonical_row_hash_artifact import CanonicalRowHashesArtifactManifest
from gateway_backend.canonical_row_hash_ipc import (
    CanonicalRowHashIpcError,
    collect_row_hashes_from_ipc,
    content_manifest_from_compute_result,
    open_row_hash_ipc_stream,
    persist_canonical_row_hash_stream,
    reopen_and_verify_canonical_row_hash_artifact,
    write_row_hash_ipc_stream,
)
from gateway_backend.compute import canonical_row_hashes_v1
from gateway_backend.infrastructure.artifact_store import LocalArtifactStore
from gateway_compute import (
    ComputeRequestError,
    _canonical_row_hashes_v1_native,
)
from gateway_shared_kernel import DigestRef

from ipc_negative_fixtures import (
    RANDOM_GARBAGE_SEED,
    append_bytes,
    build_compute_fixture,
    concat_streams,
    find_values_buffer_flip_offset,
    flip_byte_at,
    truncate_at,
)
from pr_native_support import (
    BytesOnlyArtifactStore,
    assert_failure_envelope,
    assert_public_boundary_sanitized,
    build_logical_ref_for_case,
    minimal_request_jcs,
    run_full_chain,
)

pytestmark = pytest.mark.pr_native

FIXTURE = build_compute_fixture()


class SpyArtifactStore:
    """Counts put calls while delegating to an in-memory store."""

    def __init__(self) -> None:
        self.put_calls = 0
        self._inner = InMemoryArtifactStore()

    def put(self, raw_bytes: bytes, manifest: Any) -> ArtifactRef:
        self.put_calls += 1
        return self._inner.put(raw_bytes, manifest)

    def locate(self, ref: ArtifactRef) -> bytes:
        return self._inner.locate(ref)

    def verify_manifest(self, manifest: Any) -> None:
        self._inner.verify_manifest(manifest)


def _run_compute(
    fields_json: str, data: pa.Table | pa.RecordBatch | pa.RecordBatchReader
) -> tuple[pa.RecordBatchReader, bytes]:
    return canonical_row_hashes_v1(minimal_request_jcs(fields_json), data)


def test_backend_facade_request_schema_invalid_has_stable_failure() -> None:
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(
            b"{not-json",
            pa.RecordBatchReader.from_batches(pa.schema([]), []),
        )
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="COMPUTE_REQUEST_SCHEMA_INVALID",
    )


def test_backend_facade_unsupported_physical_type_has_stable_failure() -> None:
    fields = '[{"name":"s","nullable":false,"semantic_type":{"kind":"string"}}]'
    batch = pa.record_batch([pa.array(["hello"], type=pa.large_utf8())], names=["s"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(minimal_request_jcs(fields), batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_TYPE_UNSUPPORTED",
    )


def test_backend_facade_schema_mismatch_has_stable_failure() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"boolean"}}]'
    batch = pa.record_batch([pa.array([1], type=pa.int8())], names=["v"])
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(minimal_request_jcs(fields), batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_SCHEMA_MISMATCH",
    )


def test_backend_facade_non_nullable_null_slot_has_stable_failure() -> None:
    fields = '[{"name":"v","nullable":false,"semantic_type":{"kind":"signed-integer","bits":32}}]'
    schema = pa.schema([pa.field("v", pa.int32(), nullable=False)])
    batch = pa.record_batch([pa.array([None], type=pa.int32())], schema=schema)
    with pytest.raises(ComputeRequestError) as exc_info:
        canonical_row_hashes_v1(minimal_request_jcs(fields), batch)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_STREAM_IMPORT_FAILED",
    )


def test_backend_facade_arrow_stream_import_failure_has_stable_failure() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    request_jcs = minimal_request_jcs(fields)
    with pytest.raises(ComputeRequestError) as exc_info:
        _canonical_row_hashes_v1_native(request_jcs, 42)
    assert_failure_envelope(
        exc_info.value,
        expected_type=ComputeRequestError,
        expected_code="ARROW_STREAM_IMPORT_FAILED",
    )


def test_backend_facade_rejects_invalid_python_input_before_persist() -> None:
    fields = '[{"name":"flag","nullable":true,"semantic_type":{"kind":"boolean"}}]'
    with pytest.raises(TypeError, match="data must be pyarrow"):
        canonical_row_hashes_v1(minimal_request_jcs(fields), 42)


def _make_row_hash_output_reader() -> pa.RecordBatchReader:
    schema = pa.schema([pa.field("row_hash", pa.binary(32), nullable=False)])
    batch = pa.record_batch([pa.array([b"\x00" * 32], type=pa.binary(32))], schema=schema)
    return pa.RecordBatchReader.from_batches(schema, [batch])


def _failing_finalize_stream_class(exc: Exception) -> type[pa.BufferOutputStream]:
    class FailingFinalizeStream(pa.BufferOutputStream):  # type: ignore[misc]
        def getvalue(self) -> pa.Buffer:
            raise exc

    return FailingFinalizeStream


@pytest.mark.parametrize(
    ("failure_mode", "exc"),
    [
        ("sink", pa.ArrowInvalid("private /tmp/sink-create.ipc")),
        ("stream", pa.ArrowInvalid("private /tmp/audit-secret.ipc")),
        ("finalize", pa.ArrowInvalid("private /tmp/finalize.ipc")),
        ("sink", pa.ArrowMemoryError("private /tmp/memory.ipc")),
        ("stream", pa.ArrowTypeError("private /tmp/type.ipc")),
        ("finalize", pa.ArrowCapacityError("private /tmp/capacity.ipc")),
    ],
    ids=[
        "arrow_invalid_sink",
        "arrow_invalid_stream",
        "arrow_invalid_finalize",
        "arrow_memory_sink",
        "arrow_type_stream",
        "arrow_capacity_finalize",
    ],
)
def test_ipc_writer_failure_sanitizes_pyarrow_exceptions(
    failure_mode: str,
    exc: Exception,
) -> None:
    reader = _make_row_hash_output_reader()
    if failure_mode == "sink":
        patch_ctx = patch(
            "gateway_backend.canonical_row_hash_ipc.pa.BufferOutputStream",
            side_effect=exc,
        )
    elif failure_mode == "stream":
        patch_ctx = patch(
            "gateway_backend.canonical_row_hash_ipc.pa.ipc.new_stream",
            side_effect=exc,
        )
    else:
        patch_ctx = patch(
            "gateway_backend.canonical_row_hash_ipc.pa.BufferOutputStream",
            new=_failing_finalize_stream_class(exc),
        )
    with patch_ctx:
        with pytest.raises(CanonicalRowHashIpcError, match="canonical row-hash ipc write failed"):
            write_row_hash_ipc_stream(reader)
        with pytest.raises(CanonicalRowHashIpcError) as exc_info:
            write_row_hash_ipc_stream(reader)
    assert_public_boundary_sanitized(exc_info.value)


@pytest.mark.parametrize(
    ("patch_target", "exc"),
    [
        ("pa.BufferReader", pa.ArrowMemoryError("private /tmp/read-buffer.ipc")),
        ("pa.RecordBatchReader", pa.ArrowTypeError("private /tmp/from-batches.ipc")),
    ],
    ids=["buffer_reader_memory", "from_batches_type"],
)
def test_ipc_reader_failure_sanitizes_pyarrow_exceptions(
    patch_target: str,
    exc: Exception,
) -> None:
    valid_ipc = write_row_hash_ipc_stream(_make_row_hash_output_reader())
    if patch_target == "pa.RecordBatchReader":
        with patch("gateway_backend.canonical_row_hash_ipc.pa.RecordBatchReader") as reader_cls:
            reader_cls.from_batches.side_effect = exc
            with pytest.raises(CanonicalRowHashIpcError, match="invalid arrow ipc stream"):
                open_row_hash_ipc_stream(valid_ipc)
            with pytest.raises(CanonicalRowHashIpcError) as exc_info:
                open_row_hash_ipc_stream(valid_ipc)
    else:
        with patch(
            f"gateway_backend.canonical_row_hash_ipc.{patch_target}",
            side_effect=exc,
        ):
            with pytest.raises(CanonicalRowHashIpcError, match="invalid arrow ipc stream"):
                open_row_hash_ipc_stream(valid_ipc)
            with pytest.raises(CanonicalRowHashIpcError) as exc_info:
                open_row_hash_ipc_stream(valid_ipc)
    assert_public_boundary_sanitized(exc_info.value)


def test_publish_row_count_mismatch_full_chain_has_no_put_effect() -> None:
    fields = FIXTURE.fields
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=content.table_schema_digest,
        row_count="999",
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="row_count mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref_for_case("publish-row-count"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )
    assert store.put_calls == 0


def test_publish_schema_digest_mismatch_full_chain_has_no_put_effect() -> None:
    fields = FIXTURE.fields
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=DigestRef("sha256:" + "f" * 64),
        row_count=content.row_count,
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch"):
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref_for_case("publish-schema"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )
    assert store.put_calls == 0


def test_publish_raw_content_digest_mismatch_full_chain_has_no_put_effect() -> None:
    fields = FIXTURE.fields
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True, False]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=DigestRef("sha256:" + "b" * 64),
        table_schema_digest=content.table_schema_digest,
        row_count=content.row_count,
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="raw_content_digest mismatch") as exc_info:
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref_for_case("publish-raw-digest"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )
    assert store.put_calls == 0
    assert_public_boundary_sanitized(exc_info.value)


def test_publish_failure_message_has_no_host_paths(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    tampered = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=DigestRef("sha256:" + "f" * 64),
        row_count=content.row_count,
    )
    store = SpyArtifactStore()
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch") as exc_info:
        persist_canonical_row_hash_stream(
            store,
            logical_ref=build_logical_ref_for_case("publish-boundary"),
            reader=output,
            content_manifest=tampered,
            declared_table_schema_fields=fields,
        )
    assert store.put_calls == 0
    assert_public_boundary_sanitized(exc_info.value, forbidden_path=tmp_path)


def test_full_chain_reopen_rejects_envelope_content_digest_mismatch() -> None:
    fields = FIXTURE.fields
    store = InMemoryArtifactStore()
    ref, content, _ = run_full_chain(
        store,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("envelope-digest"),
    )
    raw_bytes = store.locate(ref)
    forged_ref = replace(ref, content_digest=DigestRef("sha256:" + "d" * 64))
    with pytest.raises(
        CanonicalRowHashIpcError, match="envelope content_digest mismatch"
    ) as exc_info:
        reopen_and_verify_canonical_row_hash_artifact(
            BytesOnlyArtifactStore(raw_bytes),
            forged_ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )
    assert_public_boundary_sanitized(exc_info.value)


def test_full_chain_put_failure_sanitizes_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = FIXTURE.fields
    store = LocalArtifactStore(tmp_path / "artifacts")
    output, result_jcs = _run_compute(json.dumps(fields), pa.table({"flag": [True]}))
    content = content_manifest_from_compute_result(result_jcs)
    raw_bytes = write_row_hash_ipc_stream(output)

    def fail_replace(_source: os.PathLike[str], _target: os.PathLike[str]) -> None:
        raise OSError(f"private path: {tmp_path}")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(ManifestVerificationError, match="artifact write failed") as exc_info:
        put_with_built_manifest(
            store,
            raw_bytes,
            logical_ref=build_logical_ref_for_case("put-os-error"),
            content_manifest=content,
            retention_class=RetentionClass.OPERATION,
        )
    assert_public_boundary_sanitized(exc_info.value, forbidden_path=tmp_path)


def test_full_chain_reopen_rejects_trailing_garbage_persisted_ipc(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("trailing-garbage"),
    )
    store = LocalArtifactStore(artifact_root)
    raw_bytes = store.locate(ref)
    tampered = append_bytes(raw_bytes, RANDOM_GARBAGE_SEED)
    object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
    object_path.write_bytes(tampered)
    with pytest.raises(ManifestVerificationError):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_full_chain_reopen_rejects_concatenated_ipc_stream(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True, False]}),
        logical_ref=build_logical_ref_for_case("concat-stream"),
    )
    store = LocalArtifactStore(artifact_root)
    raw_bytes = store.locate(ref)
    tampered = concat_streams(
        raw_bytes[: len(raw_bytes) // 2],
        raw_bytes,
    )
    object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
    object_path.write_bytes(tampered)
    with pytest.raises(ManifestVerificationError):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_fresh_local_store_disk_tamper_rejects_reopen(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("fresh-tamper"),
    )
    store = LocalArtifactStore(artifact_root)
    raw_bytes = store.locate(ref)
    row_hashes = collect_row_hashes_from_ipc(raw_bytes)
    tampered = flip_byte_at(
        raw_bytes,
        find_values_buffer_flip_offset(raw_bytes, row_hashes[0]),
    )
    object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
    object_path.write_bytes(tampered)
    with pytest.raises(ManifestVerificationError, match="stored raw_sha256 mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_fresh_local_store_sidecar_identity_mismatch(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("sidecar-tamper"),
    )
    store_a = LocalArtifactStore(artifact_root)
    raw_bytes = store_a.locate(ref)
    forged_manifest = build_manifest(
        logical_ref=ref.logical_ref,
        raw_bytes=raw_bytes,
        content=CanonicalRowHashesArtifactManifest.create(
            raw_content_digest=DigestRef("sha256:" + "e" * 64),
            table_schema_digest=content.table_schema_digest,
            row_count=content.row_count,
        ),
        retention_class=RetentionClass.OPERATION,
    )
    sidecar = next(artifact_root.rglob("*.manifest.jcs"))
    sidecar.write_text(
        __import__(
            "gateway_backend.artifacts.serialize",
            fromlist=["artifact_manifest_to_json"],
        ).artifact_manifest_to_json(forged_manifest),
        encoding="utf-8",
    )
    fresh_store = LocalArtifactStore(artifact_root)
    with pytest.raises(ManifestVerificationError, match="stored artifact identity mismatch"):
        fresh_store.locate(ref)


def test_compute_failure_before_persist_has_no_put_effect() -> None:
    fields = FIXTURE.fields
    store = SpyArtifactStore()
    output: pa.RecordBatchReader | None = None
    result_jcs: bytes | None = None
    with pytest.raises(ComputeRequestError):
        output, result_jcs = _run_compute(
            json.dumps(fields),
            pa.record_batch([pa.array([1], type=pa.int8())], names=["flag"]),
        )
    assert output is None
    assert result_jcs is None
    assert store.put_calls == 0


def test_full_chain_reopen_rejects_corrupt_persisted_ipc(tmp_path: Path) -> None:
    fields = FIXTURE.fields
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fields,
        data=pa.table({"flag": [True, False]}),
        logical_ref=build_logical_ref_for_case("corrupt-reopen"),
    )
    store = LocalArtifactStore(artifact_root)
    raw_bytes = store.locate(ref)
    tampered = flip_byte_at(raw_bytes, len(raw_bytes) // 2)
    object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
    object_path.write_bytes(tampered)
    with pytest.raises(ManifestVerificationError):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_full_chain_reopen_rejects_truncated_persisted_ipc(tmp_path: Path) -> None:
    fixture = build_compute_fixture()
    artifact_root = tmp_path / "artifacts"
    ref, content, _ = run_full_chain(
        LocalArtifactStore(artifact_root),
        fields=fixture.fields,
        data=pa.table({"flag": [True, False]}),
        logical_ref=build_logical_ref_for_case("truncated-reopen"),
    )
    store = LocalArtifactStore(artifact_root)
    raw_bytes = store.locate(ref)
    truncated = truncate_at(raw_bytes, fixture.after_batch1_offset)
    object_path = store._object_path(ref.logical_ref)  # noqa: SLF001
    object_path.write_bytes(truncated)
    with pytest.raises(ManifestVerificationError):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=content,
            declared_table_schema_fields=fixture.fields,
        )


def test_full_chain_reopen_rejects_forged_size_bytes() -> None:
    fields = FIXTURE.fields
    store = InMemoryArtifactStore()
    ref, content, _ = run_full_chain(
        store,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("forged-size"),
    )
    forged_ref = replace(ref, size_bytes=ref.size_bytes + 1)
    with pytest.raises(ManifestVerificationError, match="stored artifact identity mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            forged_ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_full_chain_reopen_rejects_forged_raw_sha256() -> None:
    fields = FIXTURE.fields
    store = InMemoryArtifactStore()
    ref, content, _ = run_full_chain(
        store,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("forged-raw-sha"),
    )
    forged_ref = replace(ref, raw_sha256=DigestRef("sha256:" + "a" * 64))
    with pytest.raises(ManifestVerificationError, match="stored artifact identity mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            forged_ref,
            expected_content=content,
            declared_table_schema_fields=fields,
        )


def test_full_chain_reopen_rejects_semantic_mismatch_after_locate() -> None:
    fields = FIXTURE.fields
    store = InMemoryArtifactStore()
    ref, content, _ = run_full_chain(
        store,
        fields=fields,
        data=pa.table({"flag": [True]}),
        logical_ref=build_logical_ref_for_case("semantic-mismatch"),
    )
    forged = CanonicalRowHashesArtifactManifest.create(
        raw_content_digest=content.raw_content_digest,
        table_schema_digest=DigestRef("sha256:" + "f" * 64),
        row_count=content.row_count,
    )
    with pytest.raises(CanonicalRowHashIpcError, match="table_schema_digest mismatch"):
        reopen_and_verify_canonical_row_hash_artifact(
            store,
            ref,
            expected_content=forged,
            declared_table_schema_fields=fields,
        )
