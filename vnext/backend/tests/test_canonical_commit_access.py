"""Real HTTP Arrow session -> B/A/store recovery, bound to an exact commit."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import tempfile
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import httpx
import pyarrow as pa
import pytest

from gateway_backend.application.canonical_metadata.table_access import CanonicalCommittedTableAccess
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.capabilities.snapshot_materialization.canonical_store import CanonicalTableStore, canonical_table_key
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryProviderError, SnapshotTableDescriptor, CanonicalTableIdentity
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.repository_read.http_arrow import build_http_repository_provider_factory
from gateway_shared_kernel import raw_blob_digest
from gateway_repository_contracts import decode_commit_id_path_segment
from tests.test_canonical_table_store import BUSINESS_BUDGETS, IPC_BUDGETS, canonical_input

pytestmark = pytest.mark.unit
REPOSITORY = "d2107698-b018-463c-9dd1-9bc2bdf7bc39"
COMMIT = "exact-committed-canonical"
SQL = """CREATE TABLE t (id SMALLINT NOT NULL PRIMARY KEY, s SET('b','a'), d DATETIME(6));
INSERT INTO t VALUES (1,NULL,'2024-01-02 03:04:05'),(2,'','2024-01-02 03:04:05.123000'),
(3,'a,b','2024-01-02 03:04:05.000001'),(4,'a',NULL);"""


def _wire() -> bytes:
    schema = pa.schema([
        pa.field("id", pa.int16(), nullable=False),
        pa.field("s", pa.list_(pa.field("item", pa.string(), nullable=False))),
        pa.field("d", pa.timestamp("us")),
    ])
    batch = pa.RecordBatch.from_arrays([
        pa.array([1, 2, 3, 4], type=pa.int16()),
        pa.array([None, [], ["a", "b"], ["a"]], type=schema.field("s").type),
        pa.array([
            dt.datetime(2024, 1, 2, 3, 4, 5), dt.datetime(2024, 1, 2, 3, 4, 5, 123000),
            dt.datetime(2024, 1, 2, 3, 4, 5, 1), None,
        ], type=pa.timestamp("us")),
    ], schema=schema)
    output = io.BytesIO()
    with pa.ipc.new_stream(output, schema) as writer:
        writer.write_batch(batch)
    return output.getvalue()


def _catalog(bound: SnapshotTableDescriptor, commit: str = COMMIT) -> dict[str, object]:
    return {"commit_id": commit, "tables": [{
        "name": "t", "columns": [{"name": c.name, "sql_type": c.scalar_type, "nullable": c.nullable} for c in bound.columns],
        "primary_key": list(bound.primary_key_columns), "row_count": bound.row_count,
    }]}


def _view(bound: SnapshotTableDescriptor) -> StorageRuleView:
    record = resolve_table_rule(migrated_table_ruleset_snapshot(), "t", primary_key_columns=bound.primary_key_columns).record
    view = derive_storage_rule_view(record, bound)
    assert view is not None
    return view



def _identity(bound: SnapshotTableDescriptor) -> CanonicalTableIdentity:
    from gateway_backend.capabilities.storage_projection import compute_schema_digest
    schema = compute_schema_digest(columns=[{"name": column.name, "sql_type": column.scalar_type,
        "nullable": column.nullable} for column in bound.columns], primary_key=bound.primary_key_columns)
    assert bound.raw_content_digest is not None
    return CanonicalTableIdentity(bound.table_name, bound.row_count, bound.compare_schema_digest, schema, bound.raw_content_digest)


def test_exact_commit_recovery_hits_do_not_rewrite_and_corruption_rebuilds(db_path: Path, tmp_path: Path) -> None:
    stream, bound = canonical_input(SQL)
    stream.close()
    requests: list[str] = []
    wrong_commit = False
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        commit_segment = request.url.path.split("/commits/", 1)[1].split("/", 1)[0]
        assert decode_commit_id_path_segment(commit_segment) == COMMIT
        if request.url.path.endswith("/catalog"):
            return httpx.Response(200, json={"catalog": _catalog(bound, "wrong" if wrong_commit else COMMIT)}, headers={"X-Request-ID": "catalog"})
        return httpx.Response(200, content=_wire(), headers={"X-Request-ID": "rows", "Content-Type": "application/vnd.apache.arrow.stream"})
    providers = build_http_repository_provider_factory(
        base_url="http://repository.test", bearer_token="test-only", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    local = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(local, repository_id=REPOSITORY, budgets=IPC_BUDGETS)
    access = CanonicalCommittedTableAccess(
        store=store, unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path),
        repository_provider_factory=providers, budgets=BUSINESS_BUDGETS,
    )
    with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)) as handle:
        batch = list(handle.iter_batches())[0]
        assert batch.column(1).to_pylist() == [None, "", "b,a", "a"]
        assert batch.column(2).to_pylist() == ["2024-01-02T03:04:05", "2024-01-02T03:04:05.123", "2024-01-02T03:04:05.000001", None]
        del batch
    assert len(requests) == 2
    with ControlDbUnitOfWork(db_path) as uow:
        ref = uow.canonical_tables.lookup(canonical_table_key(REPOSITORY, bound))
    assert ref is not None
    digest = hashlib.sha256(ref.artifact_id.encode()).hexdigest()
    path = local.artifact_root / digest[:2] / digest[2:4] / digest
    before = path.stat().st_mtime_ns
    with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)) as handle:
        assert sum(batch.num_rows for batch in handle.iter_batches()) == 4
    assert len(requests) == 2 and path.stat().st_mtime_ns == before
    path.write_bytes(b"corrupt")
    with pytest.raises(ManifestVerificationError):
        store.open(ref, bound)  # Frozen owner has no source recovery path.
    assert len(requests) == 2
    with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)) as handle:
        assert sum(batch.num_rows for batch in handle.iter_batches()) == 4
    assert len(requests) == 4
    mismatched = replace(bound, raw_content_digest=raw_blob_digest(b"wrong"))
    count = len(list(local.artifact_root.rglob("*.ref.jcs")))
    with pytest.raises(ValueError, match="digest"):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=mismatched, storage_view=_view(mismatched)):
            pytest.fail("mismatched exact-commit content was published")
    assert len(list(local.artifact_root.rglob("*.ref.jcs"))) == count
    wrong_commit = True
    with pytest.raises(RepositoryProviderError, match="pinned exact commit"):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=mismatched, storage_view=_view(mismatched)):
            pytest.fail("wrong exact commit was accepted")


class _BrokenWire(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield _wire()[:128]
        raise httpx.ReadError("injected interrupted response stream")


HTTP_WIRE_FAILURES = (
    pytest.param("budget", MemoryError, "spool", id="byte-limit"),
    pytest.param("network", RepositoryProviderError, "table row read failed", id="interrupted-stream"),
)


@pytest.mark.parametrize(("wire_failure", "expected", "message"), HTTP_WIRE_FAILURES)
def test_http_arrow_source_failure_publishes_no_canonical_artifact(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    wire_failure: str, expected: type[Exception], message: str,
) -> None:
    stream, bound = canonical_input(SQL)
    stream.close()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/catalog"):
            return httpx.Response(200, json={"catalog": _catalog(bound)}, headers={"X-Request-ID": "catalog"})
        if wire_failure == "network":
            return httpx.Response(200, stream=_BrokenWire(), headers={"X-Request-ID": "rows", "Content-Type": "application/vnd.apache.arrow.stream"})
        return httpx.Response(200, content=_wire(), headers={"X-Request-ID": "rows", "Content-Type": "application/vnd.apache.arrow.stream"})
    providers = build_http_repository_provider_factory(
        base_url="http://repository.test", bearer_token="test-only", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    local = LocalArtifactStore(tmp_path / "objects")
    access = CanonicalCommittedTableAccess(
        store=CanonicalTableStore(local, repository_id=REPOSITORY, budgets=IPC_BUDGETS),
        unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path), repository_provider_factory=providers,
        budgets={**BUSINESS_BUDGETS, "max_input_bytes": 128 if wire_failure == "budget" else BUSINESS_BUDGETS["max_input_bytes"]},
    )
    with pytest.raises(expected, match=message):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)):
            pytest.fail("failed wire source was accepted")
    assert not list(tmp_path.glob("gateway-arrow-*.ipc"))
    assert not list(local.artifact_root.rglob("*.ref.jcs"))


@pytest.mark.parametrize("stop_error", (InterruptedError, TimeoutError, pa.ArrowMemoryError))
def test_cached_canonical_control_is_not_a_recovery_miss(
    db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stop_error: type[Exception],
) -> None:
    stream, bound = canonical_input()
    local = LocalArtifactStore(tmp_path / "objects")
    store = CanonicalTableStore(local, repository_id=REPOSITORY, budgets=IPC_BUDGETS)
    with stream:
        ref = store.put(stream, bound)
    with ControlDbUnitOfWork(db_path) as uow:
        uow.canonical_tables.register(canonical_table_key(REPOSITORY, bound), ref)

    def stopped(*args: object) -> None:
        raise stop_error("caller control")

    monkeypatch.setattr(store, "open", stopped)
    access = CanonicalCommittedTableAccess(
        store=store, unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path),
        repository_provider_factory=lambda *args: pytest.fail("control must not reopen the source"),
        budgets=BUSINESS_BUDGETS,
    )
    with pytest.raises(stop_error, match="caller control"):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)):
            pytest.fail("control was swallowed")


@pytest.mark.parametrize("missing", ("port", "identity"))
def test_selected_repository_tables_require_the_scoped_committed_port(missing: str) -> None:
    from tests.support.repository_ref_materialization import (
        FakeRepositoryTableAccessProvider, catalog_table, int_id_column, make_catalog, make_request,
    )
    from gateway_backend.capabilities.snapshot_materialization.repository_ref import materialize_repository_ref

    provider = FakeRepositoryTableAccessProvider(
        catalog=make_catalog((catalog_table("t", (int_id_column(),)),)), rows={"t": ((1,),)},
    )
    request = make_request(provider)
    if missing == "port":
        with pytest.raises(ValueError, match="committed canonical access"):
            materialize_repository_ref(replace(request, committed_tables=None))
    else:
        result = materialize_repository_ref(replace(request,
            canonical_binding=replace(request.canonical_binding, table_identities=())))
        assert result.status.value == "FAILED"
        assert result.diagnostics[0].message == "selected repository table is missing its canonical content identity"


def test_returned_committed_reader_cleanup_releases_mapping_after_stop(db_path: Path, tmp_path: Path) -> None:
    import threading
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, kernel_execution_scope,
    )
    from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext, NeverCancel

    stop = threading.Event()
    context = KernelExecutionContext(OperationMemoryBudget(256 * 1024**2), stop, 1)
    with kernel_execution_scope(context, new_operation=True):
        stream, bound = canonical_input()
        store = CanonicalTableStore(LocalArtifactStore(tmp_path / "objects"), repository_id=REPOSITORY, budgets=IPC_BUDGETS)
        with stream:
            ref = store.put(stream, bound)
        with ControlDbUnitOfWork(db_path) as uow:
            uow.canonical_tables.register(canonical_table_key(REPOSITORY, bound), ref)
        access = CanonicalCommittedTableAccess(
            store=store, unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path),
            repository_provider_factory=lambda *args: pytest.fail("healthy hit must not read source"), budgets=BUSINESS_BUDGETS,
        )
        table = access.load_table(commit_id=COMMIT, descriptor=bound, identity=_identity(bound), storage_view=_view(bound),
            context=ParserInvocationContext(NeverCancel()), timeout_policy=None)
        assert context.memory._mappings
        stop.set()
        assert table.reader is not None and table.batch_reader is not None
        table.reader.close()
        table.batch_reader.close()
        assert not context.memory._mappings



def test_same_value_different_catalog_type_cannot_rebind_committed_schema(db_path: Path, tmp_path: Path) -> None:
    from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext, NeverCancel
    stream, bound = canonical_input()
    stream.close()
    changed = replace(bound, columns=(replace(bound.columns[0], scalar_type="BIGINT"), *bound.columns[1:]))
    access = CanonicalCommittedTableAccess(
        store=CanonicalTableStore(LocalArtifactStore(tmp_path / "objects"), repository_id=REPOSITORY, budgets=IPC_BUDGETS),
        unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path),
        repository_provider_factory=lambda *args: pytest.fail("schema mismatch must precede source access"), budgets=BUSINESS_BUDGETS,
    )
    with pytest.raises(RepositoryProviderError, match="manifest schema/content"):
        access.load_table(commit_id=COMMIT, descriptor=changed, identity=_identity(bound), storage_view=_view(changed),
            context=ParserInvocationContext(NeverCancel()), timeout_policy=None)
