"""Real HTTP Arrow session -> B/A/store recovery, bound to an exact commit."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import tempfile
from dataclasses import replace
from pathlib import Path

import httpx
import pyarrow as pa
import pytest

from gateway_backend.application.canonical_metadata.table_access import CanonicalCommittedTableAccess
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.capabilities.snapshot_materialization.canonical_store import CanonicalTableStore, canonical_table_key
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryProviderError, SnapshotTableDescriptor
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import StorageRuleView
from gateway_backend.infrastructure.artifact_store.local_store import LocalArtifactStore
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.repository_read.http_arrow import build_http_repository_provider_factory
from gateway_shared_kernel import raw_blob_digest
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
        pa.array([None, [], ["b", "a"], ["a"]], type=schema.field("s").type),
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


def test_exact_commit_recovery_hits_do_not_rewrite_and_corruption_rebuilds(db_path: Path, tmp_path: Path) -> None:
    stream, bound = canonical_input(SQL)
    stream.close()
    requests: list[str] = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert COMMIT in request.url.path
        if request.url.path.endswith("/catalog"):
            return httpx.Response(200, json={"catalog": _catalog(bound)}, headers={"X-Request-ID": "catalog"})
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


def test_bounded_http_arrow_spool_cleans_failure_and_rejects_wrong_commit(db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stream, bound = canonical_input(SQL)
    stream.close()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    wrong_commit = False
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/catalog"):
            return httpx.Response(200, json={"catalog": _catalog(bound, "wrong" if wrong_commit else COMMIT)}, headers={"X-Request-ID": "catalog"})
        return httpx.Response(200, content=_wire(), headers={"X-Request-ID": "rows", "Content-Type": "application/vnd.apache.arrow.stream"})
    providers = build_http_repository_provider_factory(
        base_url="http://repository.test", bearer_token="test-only", timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )
    local = LocalArtifactStore(tmp_path / "objects")
    access = CanonicalCommittedTableAccess(
        store=CanonicalTableStore(local, repository_id=REPOSITORY, budgets=IPC_BUDGETS),
        unit_of_work_factory=lambda: ControlDbUnitOfWork(db_path), repository_provider_factory=providers,
        budgets={**BUSINESS_BUDGETS, "max_input_bytes": 128},
    )
    with pytest.raises(MemoryError, match="spool"):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)):
            pytest.fail("over-budget wire bytes were accepted")
    assert not list(tmp_path.glob("gateway-arrow-*.ipc"))
    assert not list(local.artifact_root.rglob("*.ref.jcs"))
    wrong_commit = True
    with pytest.raises(RepositoryProviderError, match="pinned exact commit"):
        with access.open_committed(commit_id=COMMIT, bound_descriptor=bound, storage_view=_view(bound)):
            pytest.fail("wrong exact commit was accepted")
