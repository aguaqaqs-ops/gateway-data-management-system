"""RepositoryRef provider protocol: pin, memoize, timeout, close, filter."""

from __future__ import annotations

from dataclasses import replace
import time

import pytest

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalTableIdentity,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    RepositoryColumn,
    RepositoryProviderError,
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
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def test_open_ref_deterministic_failure_mapping() -> None:
    cases = (
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
    binding = canonical_binding_for_catalog(catalog)
    full = materialize_ref(
        FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows),
        policy=MaterializationPolicy.READERS_REQUIRED,
        canonical_binding=binding,
    )
    assert full.status is SnapshotMaterializationStatus.COMPLETE
    assert full.summary is not None
    identities = tuple(
        CanonicalTableIdentity(
            canonical_table=descriptor.table_name,
            row_count=descriptor.row_count,
            source_schema_digest=descriptor.business_schema_digest,
            canonical_schema_digest=descriptor.business_schema_digest,
            raw_content_digest=descriptor.raw_content_digest,
        )
        for descriptor in full.summary.tables
        if descriptor.raw_content_digest is not None
    )
    binding = replace(binding, table_identities=identities)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows)
    result = materialize_ref(
        provider,
        policy=MaterializationPolicy.READERS_REQUIRED,
        canonical_binding=binding,
        requested_tables=("items",),
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    assert tuple(table.table_name for table in result.summary.tables) == ("items", "other")
    assert provider.last_session is not None
    assert provider.last_session.catalog_load_count == 1
    assert tuple(reader.stream_count for reader in provider.last_session.table_readers) == (1,)


@pytest.mark.parametrize("case", ("single_key", "composite_key", "keyless", "ordered", "zero_rows"))
def test_rowless_descriptor_matches_rowful_descriptor(case: str) -> None:
    ruleset = migrated_table_ruleset_snapshot()
    target_rows: tuple[tuple[object | None, ...], ...]
    if case == "single_key":
        target = catalog_table("single_items", (int_id_column(),))
        target_rows = ((1,),)
    elif case == "composite_key":
        target = catalog_table(
            "composite_items",
            (int_id_column(), text_column("region", 1)),
            primary_key=("id", "region"),
        )
        target_rows = ((1, "north"),)
    elif case == "keyless":
        target = catalog_table(
            "keyless_items",
            (text_column("value", 0),),
            primary_key=(),
        )
        target_rows = (("same",), ("same",))
    elif case == "ordered":
        target = catalog_table(
            "b1_n11_iec104_syx_list",
            (
                RepositoryColumn(name="gid", ordinal=0, scalar_type="INT UNSIGNED", nullable=False),
                RepositoryColumn(name="no", ordinal=1, scalar_type="INT", nullable=False),
                text_column("value", 2),
            ),
            primary_key=("gid",),
        )
        target_rows = ((1, 1, "first"), (2, 2, "second"))
    else:
        target = catalog_table("empty_items", (int_id_column(),), row_count=0)
        target_rows = ()

    selected = catalog_table("selected_items", (int_id_column(),))
    catalog = make_catalog((target, selected))
    rows = {target.table_name: target_rows, selected.table_name: ((9,),)}
    full_provider = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows)
    binding = canonical_binding_for_catalog(catalog, ruleset=ruleset)
    full = materialize_ref(
        full_provider,
        policy=MaterializationPolicy.READERS_REQUIRED,
        canonical_binding=binding,
        ruleset=ruleset,
    )
    assert full.status is SnapshotMaterializationStatus.COMPLETE
    assert full.summary is not None
    full_descriptors = {item.table_name: item for item in full.summary.tables}
    identities = tuple(
        CanonicalTableIdentity(
            canonical_table=item.table_name,
            row_count=item.row_count,
            source_schema_digest=item.business_schema_digest,
            canonical_schema_digest=item.business_schema_digest,
            raw_content_digest=item.raw_content_digest,
        )
        for item in full.summary.tables
        if item.raw_content_digest is not None
    )
    rowless_binding = replace(binding, table_identities=identities)

    rowless_provider = FakeRepositoryTableAccessProvider(catalog=catalog, rows=rows)
    rowless = materialize_ref(
        rowless_provider,
        policy=MaterializationPolicy.READERS_REQUIRED,
        requested_tables=("selected_items",),
        canonical_binding=rowless_binding,
        ruleset=ruleset,
    )

    assert rowless.status is SnapshotMaterializationStatus.COMPLETE
    assert rowless.summary is not None
    assert rowless.snapshot is not None and full.snapshot is not None
    assert rowless.snapshot.snapshot_digest == full.snapshot.snapshot_digest
    rowless_descriptors = {item.table_name: item for item in rowless.summary.tables}
    assert rowless_descriptors[target.table_name] == full_descriptors[target.table_name]
    assert rowless_provider.last_session is not None
    assert tuple(
        reader.catalog_table().table_name
        for reader in rowless_provider.last_session.table_readers
    ) == ("selected_items",)
    if case == "ordered":
        ordered_view = next(
            item for item in rowless_binding.tables if item.canonical_table == target.table_name
        )
        assert ordered_view.ordered_policy.value == "GID_NO_V1"


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


def test_retryable_open_ref_timeout_reaches_operation_recovery() -> None:
    table = catalog_table("items", (int_id_column(),))
    provider = FakeRepositoryTableAccessProvider(
        catalog=make_catalog((table,)),
        rows={"items": ((1,),)},
        open_timeout=True,
    )

    with pytest.raises(RepositoryProviderError) as exc_info:
        materialize_ref(provider)

    assert exc_info.value.retryable is True


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
