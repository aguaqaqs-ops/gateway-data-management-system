"""Exact metadata authority precedes independently admitted History row demands."""

from __future__ import annotations

from dataclasses import replace
from threading import Event

import pytest
from gateway_shared_kernel import SignedIntegerScalar, raw_blob_digest

from gateway_backend.capabilities.snapshot_materialization import (
    describe_repository_ref,
    ensure_committed_tables,
    materialize_repository_ref,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryProviderError,
    SnapshotMaterializationStatus,
    SnapshotTableSet,
)
from gateway_backend.capabilities.table_access import current_kernel_context
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    int_id_column,
    make_catalog,
    make_request,
)

pytestmark = pytest.mark.unit


def _request() -> tuple[FakeRepositoryTableAccessProvider, RepositoryRefMaterializationRequest]:
    provider = FakeRepositoryTableAccessProvider(
        catalog=make_catalog((catalog_table("a", (int_id_column(),)), catalog_table("z", (int_id_column(),)))),
        rows={"a": ((1,),), "z": ((2,), (3,))},
    )
    return provider, make_request(provider, policy=MaterializationPolicy.READERS_REQUIRED)


def test_complete_description_opens_no_rows_then_ensure_opens_only_the_merged_demand() -> None:
    provider, request = _request()
    result = describe_repository_ref(request)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None and result.summary is not None
    assert tuple(table.descriptor.table_name for table in result.table_set.tables) == ("a", "z")
    assert result.summary.row_count_total == 3
    assert all(table.reader is None for table in result.table_set.tables)
    assert all(not session.table_readers for session in provider.sessions)
    assert request.committed_tables is not None
    supplied = ensure_committed_tables(result.table_set,
        repository_ref=request.repository_ref, canonical_binding=request.canonical_binding,
        committed_tables=request.committed_tables, requested_tables=("z",), context=request.context)
    assert supplied.snapshot_digest == result.table_set.snapshot_digest
    assert supplied.tables[0] is result.table_set.tables[0]
    assert supplied.tables[1].reader is not None
    assert tuple(supplied.tables[1].reader.iter_rows()) == ((SignedIntegerScalar("2"),), (SignedIntegerScalar("3"),))
    assert [reader.catalog_table().table_name for session in provider.sessions for reader in session.table_readers] == ["z"]
    again = ensure_committed_tables(supplied, repository_ref=request.repository_ref,
        canonical_binding=request.canonical_binding, committed_tables=request.committed_tables,
        requested_tables=("z",), context=request.context)
    assert again.tables[1] is supplied.tables[1]
    assert len(provider.sessions) == 2
    supplied.tables[1].reader.close()
    assert supplied.tables[1].batch_reader is not None
    supplied.tables[1].batch_reader.close()


def test_bad_unrequested_manifest_is_rejected_before_any_selected_rows() -> None:
    provider, request = _request()
    identities = request.canonical_binding.table_identities
    broken = replace(identities[1], canonical_schema_digest=raw_blob_digest(b"wrong-schema"))
    request = replace(request, requested_tables=("a",),
        canonical_binding=replace(request.canonical_binding, table_identities=(identities[0], broken)))
    result = materialize_repository_ref(request)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.table_set is None
    assert "manifest schema/content" in result.diagnostics[0].message
    assert all(not session.table_readers for session in provider.sessions)


@pytest.mark.parametrize("failure", ("metadata", "cancel-at-return"))
def test_ensure_failed_return_closes_new_borrows_and_preserves_existing_reader(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    _provider, request = _request()
    stop = Event()
    request = replace(request, context=ParserInvocationContext(stop))
    described = describe_repository_ref(request)
    assert described.table_set is not None and request.committed_tables is not None
    first = ensure_committed_tables(described.table_set, repository_ref=request.repository_ref,
        canonical_binding=request.canonical_binding, committed_tables=request.committed_tables,
        requested_tables=("a",), context=request.context)
    active = current_kernel_context()
    assert active is not None
    existing_mappings = set(active.memory._mappings)
    retain = active.memory.retain_metadata

    def reject_result(value: object, size: int) -> None:
        if isinstance(value, SnapshotTableSet):
            if failure == "metadata":
                raise MemoryError("injected result metadata admission failure")
            stop.set()
        retain(value, size)

    monkeypatch.setattr(active.memory, "retain_metadata", reject_result)
    with pytest.raises(MemoryError if failure == "metadata" else InterruptedError):
        ensure_committed_tables(first, repository_ref=request.repository_ref,
            canonical_binding=request.canonical_binding, committed_tables=request.committed_tables,
            requested_tables=("a", "z"), context=request.context)
    stop.clear()
    assert set(active.memory._mappings) == existing_mappings
    assert first.tables[0].reader is not None and first.tables[0].batch_reader is not None
    assert tuple(first.tables[0].reader.iter_rows()) == ((SignedIntegerScalar("1"),),)
    assert sum(batch.num_rows for batch in first.tables[0].batch_reader.iter_record_batches()) == 1
    first.tables[0].reader.close()
    first.tables[0].batch_reader.close()


def test_ensure_rechecks_the_complete_frozen_metadata_before_admitting_new_rows() -> None:
    provider, request = _request()
    result = describe_repository_ref(request)
    assert result.table_set is not None and request.committed_tables is not None
    first, second = request.canonical_binding.table_identities
    changed_binding = replace(request.canonical_binding, table_identities=(first,
        replace(second, raw_content_digest=raw_blob_digest(b"different-authority"))))
    with pytest.raises(RepositoryProviderError, match="manifest schema/content"):
        ensure_committed_tables(result.table_set, repository_ref=request.repository_ref,
            canonical_binding=changed_binding, committed_tables=request.committed_tables,
            requested_tables=("a",), context=request.context)
    assert all(not session.table_readers for session in provider.sessions)


@pytest.mark.parametrize("mismatch", ("mutable-ref", "moved-ref", "repository"))
def test_metadata_description_cannot_accept_a_different_scope_or_commit(mismatch: str) -> None:
    provider, request = _request()
    if mismatch == "mutable-ref":
        request = replace(request, repository_ref=replace(request.repository_ref, ref="main"))
    elif mismatch == "moved-ref":
        provider.current_commit = "another-immutable-commit"
    else:
        request = replace(request, repository_ref=RepositoryRef("other-repository", request.repository_ref.ref))
    result = describe_repository_ref(request)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.table_set is None
    assert all(not session.table_readers for session in provider.sessions)
