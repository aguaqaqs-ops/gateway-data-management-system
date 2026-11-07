"""The canonical storage owner's real IPC/FS and borrowed-reader boundaries."""

from __future__ import annotations

from tests.support.native_projection import project_canonical_fixture

import hashlib
from dataclasses import replace
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pytest
from gateway_compute._native import _parse_sql_native

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.capabilities.snapshot_materialization.canonical_store import (
    CanonicalTableStore,
    canonical_table_key,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.storage_projection.native import project_arrow_table
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.table_access.contracts import NeverCancel
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_shared_kernel import raw_blob_digest
from tests.support.snapshot_materialization import materialize_sql

pytestmark = pytest.mark.unit

IPC_BUDGETS = {
    "max_rows": 100000, "max_columns": 2048, "max_descriptor_bytes": 4 * 1024 * 1024,
    "max_input_batches": 64, "max_input_bytes": 32 * 1024 * 1024,
    "max_output_bytes": 64 * 1024 * 1024, "max_codec_peak_bytes": 256 * 1024 * 1024,
}
BUSINESS_BUDGETS = {
    "max_rows": 100000, "max_columns": 2048, "max_batches": 64,
    "max_metadata_bytes": 4 * 1024 * 1024, "max_input_bytes": 32 * 1024 * 1024,
    "max_live_bytes": 256 * 1024 * 1024, "max_output_bytes": 64 * 1024 * 1024,
    "max_diagnostic_bytes": 512 * 1024,
}
SQL = "CREATE TABLE t (z INT NOT NULL PRIMARY KEY, a VARCHAR(8)); INSERT INTO t VALUES (2,'b'),(1,'a');"


def canonical_input(sql: str = SQL) -> tuple[pa.RecordBatchReader, SnapshotTableDescriptor]:
    old = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert old.table_set is not None
    rules = migrated_table_ruleset_snapshot()
    descriptor = old.table_set.tables[0].descriptor
    record = resolve_table_rule(
        rules, descriptor.table_name, primary_key_columns=descriptor.primary_key_columns,
    ).record
    view = derive_storage_rule_view(record, descriptor)
    assert view is not None
    parsed = cast(dict[str, Any], _parse_sql_native(sql.encode(), NeverCancel()))
    projected = project_arrow_table(
        parsed["tables"][0], descriptor, view, canonicalized_input=False,
        cancel_probe=NeverCancel(), budgets=BUSINESS_BUDGETS,
        deadline_monotonic=None, pool_threads=1,
    )
    oracle = project_canonical_fixture(old.table_set, rules)
    assert projected["output"] is not None
    bound = oracle.tables[0].descriptor
    assert bound.raw_content_digest is not None
    assert projected["output"]["raw_content_digest"] == bound.raw_content_digest.value
    return projected["output"]["tables"][0]["arrow_stream"], bound


@pytest.mark.parametrize("local", [False, True])
def test_independent_handles_bind_export_order_and_close(tmp_path: Path, local: bool) -> None:
    backend = LocalArtifactStore(tmp_path / "objects") if local else InMemoryArtifactStore()
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, descriptor = canonical_input()
    ref = store.put(stream, descriptor)
    first = store.open(ref, descriptor)
    with store.open(ref, descriptor) as second:
        assert first is not second
        assert second.schema.names == ["z", "a"]
        batches = list(second.iter_batches())
        assert batches[0].column(0).to_pylist() == [1, 2]
        assert batches[0].column(1).to_pylist() == ["a", "b"]
        del batches
        with second.borrow_stream() as borrowed:
            assert borrowed.read_all().num_rows == 2
        first.close()
        first.close()
        with pytest.raises(ValueError, match="closed"):
            list(first.iter_batches())
        assert sum(batch.num_rows for batch in second.iter_batches()) == 2
    with pytest.raises(ValueError, match="closed"):
        _ = second.schema


def test_borrowed_canonical_readers_keep_mapping_without_open_source_files(tmp_path: Path) -> None:
    backend = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    ref = store.put(stream, bound)
    with ExitStack() as resources:
        readers = [resources.enter_context(store.open(ref, bound)) for _ in range(96)]
        open_artifacts = []
        for descriptor in Path("/proc/self/fd").iterdir():
            try:
                target = descriptor.resolve(strict=True)
            except FileNotFoundError:
                continue
            if target.is_relative_to(backend.artifact_root):
                open_artifacts.append(target)
        assert open_artifacts == []
        for reader in readers:
            assert sum(batch.num_rows for batch in reader.iter_batches()) == 2


def test_content_identity_reuses_ddl_permutation_and_rejects_other_scope(tmp_path: Path) -> None:
    backend = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    ref = store.put(stream, bound)
    stream2, bound2 = canonical_input(
        "CREATE TABLE t (a VARCHAR(8), z INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES ('a',1),('b',2);"
    )
    assert store.put(stream2, bound2) == ref
    with store.open(ref, bound2) as handle:
        assert handle.schema.names == ["a", "z"]
    other = CanonicalTableStore(backend, repository_id="other", budgets=IPC_BUDGETS)
    with pytest.raises(ManifestVerificationError, match="identity"):
        other.open(ref, bound)


def test_mapping_uses_raw_integrity_and_bounded_profile_before_reader(tmp_path: Path) -> None:
    backend = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    ref = store.put(stream, bound)
    digest = hashlib.sha256(ref.artifact_id.encode()).hexdigest()
    path = backend.artifact_root / digest[:2] / digest[2:4] / digest
    raw = path.read_bytes()
    path.write_bytes(raw[:-1])
    with pytest.raises(ManifestVerificationError):
        store.open(ref, bound)
    corrupt = raw.replace(b'gdds.canonical_mapping_version', b'xdds.canonical_mapping_version')
    path.write_bytes(corrupt)
    # Exact integrity is insufficient when the bound internal profile differs.
    changed = replace(ref, raw_sha256=raw_blob_digest(corrupt))
    fresh = InMemoryArtifactStore()
    fresh.put(corrupt, changed)
    with pytest.raises(ValueError, match="metadata"):
        CanonicalTableStore(fresh, repository_id="repo", budgets=IPC_BUDGETS).open(changed, bound)
    bounded = CanonicalTableStore(fresh, repository_id="repo", budgets={**IPC_BUDGETS, "max_input_bytes": 1})
    with pytest.raises(MemoryError, match="input"):
        bounded.open(changed, bound)


def test_failed_stream_and_wrong_row_binding_publish_no_object(tmp_path: Path) -> None:
    backend = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    with pytest.raises(ValueError, match="row count"):
        store.put(stream, replace(bound, row_count=3))
    assert not list(backend.artifact_root.rglob("*.ref.jcs"))
    assert canonical_table_key("repo", bound).artifact_id.startswith("canonical-table:")


def test_binding_cannot_open_a_different_business_digest(tmp_path: Path) -> None:
    backend = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    ref: ArtifactRef = store.put(stream, bound)
    with pytest.raises(ManifestVerificationError, match="identity"):
        store.open(ref, replace(bound, raw_content_digest=raw_blob_digest(b"other")))


def test_handle_stream_is_borrowed_by_the_real_projection_kernel(tmp_path: Path) -> None:
    store = CanonicalTableStore(LocalArtifactStore(tmp_path / "objects"), repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    assert bound.raw_content_digest is not None
    ref = store.put(stream, bound)
    rules = migrated_table_ruleset_snapshot()
    record = resolve_table_rule(rules, bound.table_name, primary_key_columns=bound.primary_key_columns).record
    view = derive_storage_rule_view(record, bound)
    assert view is not None
    from gateway_backend.capabilities.snapshot_materialization import canonical_columns
    with store.open(ref, bound) as handle:
        with handle.borrow_stream() as borrowed:
            result = project_arrow_table({
                "canonical_name": bound.table_name, "display_name": bound.display_table_name,
                "columns": canonical_columns(bound), "primary_key": list(bound.primary_key_columns),
                "reader_ready": True, "arrow_stream": borrowed,
            }, bound, view, canonicalized_input=True, cancel_probe=NeverCancel(), budgets=BUSINESS_BUDGETS,
                deadline_monotonic=None, pool_threads=1)
            assert result["output"]["raw_content_digest"] == bound.raw_content_digest.value
            result["output"]["tables"][0]["arrow_stream"].close()
    with pytest.raises(ValueError, match="closed"):
        _ = handle.schema


def test_empty_schema_and_primary_key_metadata_are_bounded_before_key_hash(tmp_path: Path) -> None:
    stream, bound = canonical_input()
    stream.close()
    store = CanonicalTableStore(InMemoryArtifactStore(), repository_id="repo", budgets={**IPC_BUDGETS, "max_descriptor_bytes": 1})
    empty = replace(bound, columns=(), primary_key_columns=())
    ref = ArtifactRef(canonical_table_key("repo", empty).artifact_id, "application/vnd.apache.arrow.file", 0, raw_blob_digest(b""))
    with pytest.raises(MemoryError, match="descriptor"):
        store.open(ref, empty)
    keys = replace(bound, primary_key_columns=("x" * (4 * 1024 * 1024),))
    with pytest.raises(MemoryError, match="descriptor"):
        store.put(pa.RecordBatchReader.from_batches(pa.schema([]), []), keys)


@pytest.mark.parametrize("outside", [False, True])
def test_canonical_mapping_refuses_symlinks(tmp_path: Path, outside: bool) -> None:
    local = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(local, repository_id="repo", budgets=IPC_BUDGETS)
    stream, bound = canonical_input()
    ref = store.put(stream, bound)
    digest = hashlib.sha256(ref.artifact_id.encode()).hexdigest()
    path = local.artifact_root / digest[:2] / digest[2:4] / digest
    target = (tmp_path if outside else local.artifact_root) / "other-file"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ManifestVerificationError):
        store.open(ref, bound)


def test_operation_mapping_reservations_share_views_and_count_independent_opens(tmp_path: Path) -> None:
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, kernel_execution_scope,
    )

    context = KernelExecutionContext(OperationMemoryBudget(64 * 1024**2), NeverCancel(), 1)
    with kernel_execution_scope(context, new_operation=True):
        backend = LocalArtifactStore(tmp_path / "objects")
        store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
        stream, descriptor = canonical_input(
            "CREATE TABLE t (z INT NOT NULL PRIMARY KEY, a TEXT); INSERT INTO t VALUES (1,'" + "a" * 131072 + "');"
        )
        ref = store.put(stream, descriptor)
        before = context.memory.used_bytes
        with store.open(ref, descriptor) as first:
            one_mapping = context.memory.used_bytes
            with first.borrow_stream() as borrowed:
                arrays = borrowed.read_all()
            with context.memory.retain_arrow(arrays):
                assert context.memory.used_bytes - one_mapping < ref.size_bytes
                with store.open(ref, descriptor):
                    assert context.memory.used_bytes - one_mapping >= ref.size_bytes
            del arrays
        assert context.memory.used_bytes == before


def test_operation_stop_at_eof_prevents_canonical_publication(tmp_path: Path) -> None:
    import threading

    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, kernel_execution_scope,
    )

    stream, descriptor = canonical_input()
    with stream:
        arrays = stream.read_all()
    stopped = threading.Event()
    context = KernelExecutionContext(OperationMemoryBudget(16 * 1024**2), stopped, 1)
    backend = LocalArtifactStore(tmp_path / "objects")
    called = []

    def batches() -> Iterator[pa.RecordBatch]:
        yield from arrays.to_batches()
        stopped.set()

    with kernel_execution_scope(context, new_operation=True):
        store = CanonicalTableStore(backend, repository_id="repo", budgets=IPC_BUDGETS)
        with pa.RecordBatchReader.from_batches(arrays.schema, batches()) as source:
            with pytest.raises(InterruptedError):
                store.put(source, descriptor, before_write=lambda key, ref: called.append(ref))
    assert called == []
    assert not any(path.is_file() for path in backend.artifact_root.rglob("*"))


def test_canonical_snapshot_manifest_requires_the_callers_repository_and_ipc_format() -> None:
    from gateway_backend.capabilities.snapshot_materialization import (
        publish_canonical_tables, open_snapshot_table_artifact, snapshot_table_from_arrow,
        source_descriptor_from_arrow, canonical_columns,
    )
    from gateway_backend.capabilities.snapshot_materialization.artifact import ArtifactPublishError, manifest_from_bytes
    from gateway_shared_kernel import DigestRef

    stream, descriptor = canonical_input()
    with stream:
        arrays = stream.read_all()
    source = source_descriptor_from_arrow({"canonical_name": descriptor.table_name,
        "display_name": descriptor.display_table_name, "columns": canonical_columns(descriptor),
        "primary_key": list(descriptor.primary_key_columns), "reader_ready": True})
    table = snapshot_table_from_arrow(descriptor, arrays, source)
    class WriterStore(InMemoryArtifactStore):
        reads = 0

        def open_buffer(self, ref: ArtifactRef, *, checkpoint: Any = None) -> Any:
            self.reads += 1
            return super().open_buffer(ref, checkpoint=checkpoint)

    store = WriterStore()
    published = publish_canonical_tables((table,), snapshot_digest=DigestRef("sha256:" + "0" * 64),
                                        store=store, repository_id="repo")[0]
    assert store.reads == 0
    assert published.reader is not None
    table.reader.close()  # type: ignore[union-attr]
    assert tuple(published.reader.iter_rows())
    assert store.reads == 0
    assert published.artifact is not None
    manifest = published.artifact.manifest
    assert manifest.row_format == "arrow-ipc"
    assert manifest.compression == "none"
    assert manifest.repository_id == "repo"
    for repository_id in (None, "other"):
        with pytest.raises(ArtifactPublishError):
            open_snapshot_table_artifact(store, published.artifact.manifest_ref,
                                         repository_id=repository_id, canonical_required=True)
    opened = open_snapshot_table_artifact(store, published.artifact.manifest_ref,
                                         repository_id="repo", canonical_required=True)
    assert opened.reader is not None
    assert tuple(opened.reader.iter_rows())
    import json
    payload = json.loads(store.locate(published.artifact.manifest_ref))
    del payload["repository_id"]
    with pytest.raises(KeyError):
        manifest_from_bytes(json.dumps(payload).encode())


def test_client_export_preserves_parquet_profile_and_reuses_scoped_layout_cache(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.capabilities.snapshot_materialization import (
        publish_canonical_tables, snapshot_table_from_arrow, source_descriptor_from_arrow, canonical_columns,
        export_snapshot_table_parquet,
    )
    from gateway_backend.capabilities.snapshot_materialization._parquet import read_parquet_table, encoding_columns_from_table, iter_decoded_rows
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from gateway_backend.infrastructure.control_db.snapshot_export_cache import ControlDbSnapshotTableExportCache
    from gateway_shared_kernel import DigestRef, Float32Scalar
    from gateway_backend.capabilities.table_access.contracts import SqlSetValue

    sql = """CREATE TABLE t (id SMALLINT NOT NULL PRIMARY KEY, s SET('b','a'), f FLOAT, d DATETIME(6));
        INSERT INTO t VALUES (1,'a,b',1.25,'2024-01-02 03:04:05.123000'),(2,'',NULL,NULL),(3,NULL,-0.0,NULL);"""
    stream, descriptor = canonical_input(sql)
    with stream:
        backing = stream.read_all()
    source = source_descriptor_from_arrow({"canonical_name": descriptor.table_name,
        "display_name": descriptor.display_table_name, "columns": canonical_columns(descriptor),
        "primary_key": list(descriptor.primary_key_columns), "reader_ready": True})
    table = snapshot_table_from_arrow(descriptor, backing, source)
    store = InMemoryArtifactStore()
    table = publish_canonical_tables((table,), snapshot_digest=DigestRef("sha256:" + "0" * 64), store=store, repository_id="repo")[0]
    cache = ControlDbSnapshotTableExportCache(lambda: ControlDbUnitOfWork(db_path))
    ref = export_snapshot_table_parquet(table, store=store, repository_id="repo", export_cache=cache)
    raw = store.locate(ref)
    assert raw[:4] == raw[-4:] == b"PAR1"
    exported = read_parquet_table(raw)
    assert exported.column_names == ["id", "s", "f", "d"]
    assert exported.schema.field("id").type == pa.string()
    assert exported.schema.field("s").type == pa.list_(pa.string())
    assert exported.schema.field("f").type == pa.string()
    rows = iter_decoded_rows(exported, encoding_columns_from_table(exported))
    assert rows[0][1] == SqlSetValue(("b", "a"))
    assert rows[1][1] == SqlSetValue(())
    assert rows[0][2] == Float32Scalar("3fa00000")
    def forbid_write(*args: object, **kwargs: object) -> None:
        pytest.fail("healthy client cache hit must not rewrite the artifact")
    monkeypatch.setattr(store, "put", forbid_write)
    assert export_snapshot_table_parquet(table, store=store, repository_id="repo", export_cache=cache) == ref
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, KernelMemoryLimit, kernel_execution_scope,
    )
    with kernel_execution_scope(KernelExecutionContext(OperationMemoryBudget(128 * 1024), NeverCancel(), 1), new_operation=True):
        with monkeypatch.context() as guarded:
            guarded.setattr("gateway_backend.capabilities.snapshot_materialization.client_parquet.pq.ParquetFile", forbid_write)
            with pytest.raises(KernelMemoryLimit):
                export_snapshot_table_parquet(table, store=store, repository_id="repo", export_cache=cache)
    with pytest.raises(ValueError, match="scoped canonical"):
        export_snapshot_table_parquet(table, store=store, repository_id="other", export_cache=cache)
