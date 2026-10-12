"""RepositoryRef provider protocol: pin, memoize, timeout, close, filter."""

from __future__ import annotations

import time

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    RepositoryRef,
    SnapshotMaterializationStatus,
    SourceKind,
)
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from tests.support.repository_ref_materialization import (
    DEFAULT_REF,
    FakeRepositoryTableAccessProvider,
    canonical_binding_for_catalog,
    catalog_table,
    int_id_column,
    make_catalog,
    materialize_ref,
    minimal_fixture,
    text_column,
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def test_open_ref_timeout_and_failure_mapping() -> None:
    cases = (
        ("open_timeout", MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_TIMEOUT),
        ("open_not_found", MaterializationDiagnosticCode.REPOSITORY_REF_NOT_FOUND),
        ("open_failed", MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED),
    )
    table = catalog_table("items", (int_id_column(),))
    catalog = make_catalog((table,))
    for flag, code in cases:
        provider = FakeRepositoryTableAccessProvider(
            catalog=catalog,
            rows={"items": ((1,),)},
            open_timeout=flag == "open_timeout",
            open_not_found=flag == "open_not_found",
            open_failed=flag == "open_failed",
        )
        result = materialize_ref(provider)
        assert result.status is SnapshotMaterializationStatus.FAILED
        assert result.snapshot is None
        assert result.diagnostics[0].code is code


def test_close_is_idempotent_and_always_runs() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    session = provider.last_session
    assert session is not None
    assert session.close_count == 1
    session.close()
    assert session.close_count == 2


def test_close_failure_does_not_change_digest() -> None:
    provider, _rows = minimal_fixture()
    provider.close_error = True
    first = materialize_ref(
        FakeRepositoryTableAccessProvider(
            catalog=provider.catalog, rows=provider.rows
        )
    )
    second = materialize_ref(provider)
    assert first.status is SnapshotMaterializationStatus.COMPLETE
    assert second.status is SnapshotMaterializationStatus.COMPLETE
    assert first.snapshot is not None and second.snapshot is not None
    assert first.snapshot.snapshot_digest == second.snapshot.snapshot_digest
    assert any(
        item.code is MaterializationDiagnosticCode.REPOSITORY_SESSION_CLOSE_FAILED
        for item in second.diagnostics
    )


def test_catalog_is_memoized_within_session() -> None:
    provider, _rows = minimal_fixture()
    session = provider.open_ref(
        RepositoryRef(repository_id="repo-s4", ref=DEFAULT_REF), None
    )
    first = session.get_catalog()
    second = session.get_catalog()
    assert first is second
    assert session.catalog_load_count == 1
    session.close()


def test_materialize_loads_catalog_once() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(provider, requested_tables=("items",))
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert provider.last_session is not None
    assert provider.last_session.catalog_load_count == 1


def test_requested_tables_filter_does_not_relist() -> None:
    extra = catalog_table("other", (int_id_column(),))
    items = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"),), "other": ((9,),)}
    catalog = make_catalog((items, extra))
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows)
    result = materialize_ref(provider, requested_tables=("items",))
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    assert tuple(table.table_name for table in result.summary.tables) == ("items",)
    assert provider.last_session is not None
    assert provider.last_session.catalog_load_count == 1
    assert tuple(reader.stream_count for reader in provider.last_session.table_readers) == (1,)


def test_catalog_row_count_mismatch_is_a_regular_failure() -> None:
    table = catalog_table("items", (int_id_column(),), row_count=2)
    provider = FakeRepositoryTableAccessProvider(
        catalog=make_catalog((table,)),
        rows={"items": ((1,),)},
    )

    result = materialize_ref(provider)

    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is (
        MaterializationDiagnosticCode.REPOSITORY_ROW_COUNT_MISMATCH
    )
    assert provider.last_session is not None
    assert tuple(reader.stream_count for reader in provider.last_session.table_readers) == (1,)


def test_initial_binding_rejects_repository_user_tables() -> None:
    table = catalog_table("items", (int_id_column(),))
    catalog = make_catalog((table,))
    provider = FakeRepositoryTableAccessProvider(
        catalog=catalog,
        rows={"items": ((1,),)},
    )

    result = materialize_ref(
        provider,
        canonical_binding=canonical_binding_for_catalog(catalog, is_initial=True),
    )

    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is (
        MaterializationDiagnosticCode.INITIAL_BASELINE_NOT_EMPTY
    )
    assert provider.last_session is not None
    assert provider.last_session.table_readers == []


def test_session_stays_pinned_after_ref_moves() -> None:
    provider, _rows = minimal_fixture()
    session = provider.open_ref(
        RepositoryRef(repository_id="repo-s4", ref=DEFAULT_REF), None
    )
    provider.current_commit = "ffffffffffffffffffffffffffffffff"
    catalog = session.get_catalog()
    assert session.pinned_commit_hash() == DEFAULT_REF
    assert catalog.resolved_commit_hash == DEFAULT_REF
    session.close()


def test_source_kind_is_immutable_repository_ref() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(provider)
    assert result.snapshot is not None
    assert result.snapshot.source_kind is SourceKind.IMMUTABLE_REPOSITORY_REF
    assert result.snapshot.source_context.resolved_commit_hash == DEFAULT_REF


def test_artifacts_required_fails_closed() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(provider, policy=MaterializationPolicy.ARTIFACTS_REQUIRED)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is (
        MaterializationDiagnosticCode.ARTIFACT_STORE_REQUIRED
    )


def test_cancel_fails_closed_and_closes_session() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(
        provider, context=ParserInvocationContext(CountCancel(3))
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED
    assert provider.last_session is not None
    assert provider.last_session.close_count == 1


def test_deadline_fails_closed() -> None:
    provider, _rows = minimal_fixture()
    result = materialize_ref(
        provider,
        context=ParserInvocationContext(CountCancel(10_000), time.monotonic() - 1.0),
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT


def test_catalog_load_failure_is_failed() -> None:
    provider, _rows = minimal_fixture()
    provider.catalog_error = True
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED
    assert provider.last_session is not None
    assert provider.last_session.close_count == 1
