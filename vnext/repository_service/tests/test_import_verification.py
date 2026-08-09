"""Tests for Versioned import candidate verification."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    SqlValueConversionError,
    TableCatalog,
    arrow_type,
    record_batch,
)
from gateway_repository_service.fixtures import Workload, generate_fixture
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.models import (
    ImportManifest,
    ImportManifestColumn,
    ImportManifestSchema,
    ImportManifestTable,
    derive_operation_marker,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.ports import VersionedImportProvider
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.verification import (
    IMPORT_REJECTED_CODE,
    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
    ImportVerificationError,
    ImportVerificationResult,
    verify_import_candidate,
)
from support.lifecycle_harness import lifecycle_settings

OPERATION_ID = UUID("00000000-0000-4000-8000-0000000000b1")

UNKNOWN_NULLABLE_ARROW_FIELD = pa.field(
    "unknown_value",
    pa.large_string(),
    nullable=True,
    metadata={b"gateway.sql_type": b"ENUM('a','b')", b"gateway.lossy": b"true"},
)
UNKNOWN_NOT_NULL_ARROW_FIELD = pa.field(
    "unknown_value",
    pa.large_string(),
    nullable=False,
    metadata={b"gateway.sql_type": b"ENUM('a','b')", b"gateway.lossy": b"true"},
)


@pytest.fixture
def import_layout(tmp_path: Path) -> DurableLayout:
    settings = lifecycle_settings(tmp_path)
    return DurableLayout.create_for_probe(settings.data_root)


@pytest.fixture
def import_provider(import_layout: DurableLayout) -> CandidateAImportProvider:
    settings = lifecycle_settings(import_layout.root.parent)
    repository = import_layout.staging_artifacts / "import-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, import_layout.root)
    cli = OfflineCliProvider(settings, import_layout, repository, runner)
    cli.initialize_repository()
    return CandidateAImportProvider(settings, import_layout, repository, runner)


def manifest_from_tables(
    tables: tuple[TableCatalog, ...],
    *,
    digest: str = "manifest-digest-1",
) -> ImportManifest:
    sorted_tables = tuple(sorted(tables, key=lambda table: table.name.encode("utf-8")))
    manifest_tables: list[ImportManifestTable] = []
    for table in sorted_tables:
        manifest_tables.append(
            ImportManifestTable(
                name=table.name,
                schema=ImportManifestSchema(
                    columns=tuple(
                        ImportManifestColumn(
                            name=column.name,
                            sql_type=column.sql_type,
                            nullable=column.nullable,
                        )
                        for column in table.columns
                    ),
                    primary_key=table.primary_key,
                ),
                row_count=table.row_count,
            )
        )
    return ImportManifest(
        package_version=1,
        canonicalization_manifest_digest=digest,
        tables=tuple(manifest_tables),
    )


def _candidate_from_replay(
    provider: CandidateAImportProvider,
    layout: DurableLayout,
    replay_sql: Path,
) -> str:
    staging_path = layout.staging_artifacts / replay_sql.name
    staging_path.write_bytes(replay_sql.read_bytes())
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = provider.read_ref("main")
    provider.create_private_ref(private_ref, expected)
    provider.checkout_private_ref(private_ref)
    provider.replay_sql(private_ref, staging_path)
    return provider.commit_operation_marker(private_ref, marker)


def _tables_without_unknown(tables: tuple[TableCatalog, ...]) -> tuple[TableCatalog, ...]:
    return tuple(table for table in tables if table.name != "unknown_types")


def _wrong_row_count_manifest(manifest: ImportManifest, *, table_name: str, row_count: int) -> ImportManifest:
    updated_tables: list[ImportManifestTable] = []
    for table in manifest.tables:
        if table.name == table_name:
            updated_tables.append(table.model_copy(update={"row_count": row_count}))
        else:
            updated_tables.append(table)
    return manifest.model_copy(update={"tables": tuple(updated_tables)})


def _assert_full_scan_arrow_contracts(
    provider: CandidateAImportProvider,
    candidate: str,
    catalog: tuple[TableCatalog, ...],
    *,
    unknown_type_policy: UnknownTypePolicy,
) -> None:
    for table in catalog:
        batches = list(provider.stream_table(candidate, table, unknown_type_policy))
        assert batches
        batch = pa.concat_batches(batches)
        for index, column in enumerate(table.columns):
            field = batch.schema.field(index)
            expected_type, expected_metadata = arrow_type(column.sql_type, unknown_type_policy)
            assert field.name == column.name
            assert field.type == expected_type
            assert field.nullable == column.nullable
            assert (field.metadata or {}) == (expected_metadata or {})


@pytest.mark.parametrize(
    (
        "verification_policy",
        "unknown_type_policy",
        "catalog_kind",
        "manifest_kind",
        "expected_code",
    ),
    [
        pytest.param(
            VerificationPolicy.NONE,
            UnknownTypePolicy.REJECT,
            "known_only",
            "wrong_row_count",
            None,
            id="none-reject-skips-structural",
        ),
        pytest.param(
            VerificationPolicy.NONE,
            UnknownTypePolicy.REJECT,
            "with_unknown",
            "full",
            IMPORT_REJECTED_CODE,
            id="none-reject-rejects-unknown",
        ),
        pytest.param(
            VerificationPolicy.NONE,
            UnknownTypePolicy.STRINGIFY,
            "with_unknown",
            "wrong_row_count",
            None,
            id="none-stringify-skips-all",
        ),
        pytest.param(
            VerificationPolicy.STRUCTURAL,
            UnknownTypePolicy.REJECT,
            "known_only",
            "exact",
            None,
            id="structural-reject-known-only",
        ),
        pytest.param(
            VerificationPolicy.STRUCTURAL,
            UnknownTypePolicy.REJECT,
            "with_unknown",
            "full",
            IMPORT_REJECTED_CODE,
            id="structural-reject-rejects-unknown",
        ),
        pytest.param(
            VerificationPolicy.STRUCTURAL,
            UnknownTypePolicy.STRINGIFY,
            "with_unknown",
            "exact",
            None,
            id="structural-stringify-exact-match",
        ),
        pytest.param(
            VerificationPolicy.FULL_SCAN,
            UnknownTypePolicy.REJECT,
            "with_unknown",
            "full",
            IMPORT_REJECTED_CODE,
            id="full-scan-reject-rejects-unknown",
        ),
        pytest.param(
            VerificationPolicy.FULL_SCAN,
            UnknownTypePolicy.REJECT,
            "known_only",
            "exact",
            None,
            id="full-scan-reject-known-only",
        ),
        pytest.param(
            VerificationPolicy.FULL_SCAN,
            UnknownTypePolicy.STRINGIFY,
            "with_unknown",
            "exact",
            None,
            id="full-scan-stringify-scans-rows",
        ),
    ],
)
@pytest.mark.integration
def test_verification_policy_matrix(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
    verification_policy: VerificationPolicy,
    unknown_type_policy: UnknownTypePolicy,
    catalog_kind: str,
    manifest_kind: str,
    expected_code: str | None,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    if catalog_kind == "known_only":
        replay_sql = import_layout.staging_artifacts / "known-only.replay.sql"
        full_sql = fixture.replay_sql.read_text(encoding="utf-8")
        filtered_lines = [
            line
            for line in full_sql.splitlines(keepends=True)
            if not line.lstrip().startswith("CREATE TABLE unknown_types")
            and not line.lstrip().startswith("INSERT INTO unknown_types")
        ]
        replay_sql.write_text("".join(filtered_lines), encoding="utf-8")
    else:
        replay_sql = fixture.replay_sql

    candidate = _candidate_from_replay(import_provider, import_layout, replay_sql)
    catalog = import_provider.read_catalog(candidate)
    base_tables = (
        _tables_without_unknown(fixture.expected_tables)
        if catalog_kind == "known_only"
        else fixture.expected_tables
    )

    manifest = manifest_from_tables(base_tables)
    if manifest_kind == "wrong_row_count":
        manifest = _wrong_row_count_manifest(
            manifest,
            table_name=manifest.tables[0].name,
            row_count=manifest.tables[0].row_count + 99,
        )

    if expected_code is None:
        result = verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=verification_policy,
            unknown_type_policy=unknown_type_policy,
        )
        assert result == ImportVerificationResult(
            completed_verification_policy=verification_policy,
            unknown_type_policy=unknown_type_policy,
        )
        if verification_policy == VerificationPolicy.FULL_SCAN:
            _assert_full_scan_arrow_contracts(
                import_provider,
                candidate,
                catalog,
                unknown_type_policy=unknown_type_policy,
            )
            if unknown_type_policy == UnknownTypePolicy.STRINGIFY:
                _assert_nullable_unknown_stringify_metadata(import_provider, candidate, catalog)
    else:
        with pytest.raises(ImportVerificationError) as exc_info:
            verify_import_candidate(
                import_provider,
                candidate=candidate,
                manifest=manifest,
                verification_policy=verification_policy,
                unknown_type_policy=unknown_type_policy,
            )
        assert exc_info.value.code == expected_code


def _assert_nullable_unknown_stringify_metadata(
    provider: CandidateAImportProvider,
    candidate: str,
    catalog: tuple[TableCatalog, ...],
) -> None:
    unknown_table = next(table for table in catalog if table.name == "unknown_types")
    batches = list(provider.stream_table(candidate, unknown_table, UnknownTypePolicy.STRINGIFY))
    assert batches
    batch = batches[0]
    field = batch.schema.field("unknown_value")
    assert field.equals(UNKNOWN_NULLABLE_ARROW_FIELD)
    values = batch.column("unknown_value").to_pylist()
    assert values == ["a", None]


@pytest.mark.integration
def test_none_reject_uses_minimal_type_projection_without_row_counts(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    replay_sql = import_layout.staging_artifacts / "known-only.replay.sql"
    full_sql = fixture.replay_sql.read_text(encoding="utf-8")
    filtered_lines = [
        line
        for line in full_sql.splitlines(keepends=True)
        if not line.lstrip().startswith("CREATE TABLE unknown_types")
        and not line.lstrip().startswith("INSERT INTO unknown_types")
    ]
    replay_sql.write_text("".join(filtered_lines), encoding="utf-8")
    candidate = _candidate_from_replay(import_provider, import_layout, replay_sql)
    manifest = manifest_from_tables(_tables_without_unknown(fixture.expected_tables))
    issued_kinds: list[str] = []
    original_query_json = import_provider._cli.query_json

    def recording_query_json(kind: str, sql: str, *, revision: str | None = None) -> list[dict[str, object]]:
        issued_kinds.append(kind)
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=recording_query_json):
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.NONE,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )

    assert "catalog_count" not in issued_kinds
    assert "catalog_create" in issued_kinds


@pytest.mark.integration
def test_structural_rejects_distinct_enum_literal_spelling(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
) -> None:
    sql = """
CREATE TABLE lower_enum (id INT NOT NULL PRIMARY KEY, v ENUM('a','b') NULL);
INSERT INTO lower_enum VALUES (1, 'a');
CREATE TABLE upper_enum (id INT NOT NULL PRIMARY KEY, v ENUM('A','B') NULL);
INSERT INTO upper_enum VALUES (1, 'A');
"""
    candidate = _candidate_from_replay(
        import_provider,
        import_layout,
        _write_staging_sql(import_layout, "enum-spelling.sql", sql),
    )
    catalog = import_provider.read_catalog(candidate)
    lower = next(table for table in catalog if table.name == "lower_enum")
    upper = next(table for table in catalog if table.name == "upper_enum")
    if lower.columns[1].sql_type == upper.columns[1].sql_type:
        pytest.skip("Dolt SHOW CREATE normalized both ENUM spellings to the same catalog type")

    manifest = manifest_from_tables((upper,))
    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


@pytest.mark.integration
def test_full_scan_stringify_not_null_unknown_follows_catalog_nullability(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
) -> None:
    sql = """
CREATE TABLE required_enum (id INT NOT NULL PRIMARY KEY, unknown_value ENUM('a','b') NOT NULL);
INSERT INTO required_enum VALUES (1, 'a');
"""
    candidate = _candidate_from_replay(
        import_provider,
        import_layout,
        _write_staging_sql(import_layout, "required-enum.sql", sql),
    )
    catalog = import_provider.read_catalog(candidate)
    table = catalog[0]
    manifest = manifest_from_tables((table,))
    verify_import_candidate(
        import_provider,
        candidate=candidate,
        manifest=manifest,
        verification_policy=VerificationPolicy.FULL_SCAN,
        unknown_type_policy=UnknownTypePolicy.STRINGIFY,
    )
    batch = next(iter(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY)))
    field = batch.schema.field("unknown_value")
    assert field.equals(UNKNOWN_NOT_NULL_ARROW_FIELD)


def _write_staging_sql(layout: DurableLayout, name: str, sql: str) -> Path:
    path = layout.staging_artifacts / name
    path.write_text(sql, encoding="utf-8")
    return path


@pytest.mark.integration
def test_structural_mismatch_raises_verification_failed(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    candidate = _candidate_from_replay(import_provider, import_layout, fixture.replay_sql)
    manifest = manifest_from_tables(_tables_without_unknown(fixture.expected_tables))

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


@pytest.mark.integration
def test_full_scan_row_count_mismatch_raises(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    candidate = _candidate_from_replay(import_provider, import_layout, fixture.replay_sql)
    manifest = _wrong_row_count_manifest(
        manifest_from_tables(fixture.expected_tables),
        table_name="known_types",
        row_count=999,
    )

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


def test_structural_unknown_spelling_must_match_exactly() -> None:
    class FakeProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return (
                TableCatalog(
                    "records",
                    (
                        ColumnCatalog("id", "INT", False, 1),
                        ColumnCatalog("value", "ENUM('A','B')", True, None),
                    ),
                    0,
                ),
            )

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return self.read_catalog(candidate)

        def stream_table(self, *_args: object, **_kwargs: object) -> list[object]:
            return []

    manifest = manifest_from_tables(
        (
            TableCatalog(
                "records",
                (
                    ColumnCatalog("id", "INT", False, 1),
                    ColumnCatalog("value", "ENUM('a','b')", True, None),
                ),
                0,
            ),
        )
    )

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            cast(VersionedImportProvider, FakeProvider()),
            candidate="candidate",
            manifest=manifest,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


@pytest.mark.parametrize(
    "verification_policy",
    [
        VerificationPolicy.STRUCTURAL,
        VerificationPolicy.NONE,
    ],
)
def test_provider_fault_escapes_unchanged_from_read_catalog(
    verification_policy: VerificationPolicy,
) -> None:
    class FaultingProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            raise ImportProviderError("dolt catalog process died")

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            raise ImportProviderError("dolt catalog process died")

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})

    manifest = manifest_from_tables(
        (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 0),)
    )

    with pytest.raises(ImportProviderError, match="dolt catalog process died"):
        verify_import_candidate(
            cast(VersionedImportProvider, FaultingProvider()),
            candidate="candidate",
            manifest=manifest,
            verification_policy=verification_policy,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )


def test_provider_fault_escapes_unchanged_from_stream_table() -> None:
    class FaultingProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            table = TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1)
            return (table,)

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return self.read_catalog(candidate)

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            raise ImportProviderError("dolt row stream died")
            yield pa.record_batch({"id": pa.array([1], type=pa.int32())})

    table = TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1)
    manifest = manifest_from_tables((table,))

    with pytest.raises(ImportProviderError, match="dolt row stream died"):
        verify_import_candidate(
            cast(VersionedImportProvider, FaultingProvider()),
            candidate="candidate",
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )


def test_full_scan_batch_contract_mismatch_raises_verification_failed() -> None:
    class ContractMismatchProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1),)

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return self.read_catalog(candidate)

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            yield pa.record_batch({"id": pa.array([1], type=pa.int64())})

    table = TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1)
    manifest = manifest_from_tables((table,))

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            cast(VersionedImportProvider, ContractMismatchProvider()),
            candidate="candidate",
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


@pytest.mark.parametrize(
    "verification_policy",
    [VerificationPolicy.STRUCTURAL, VerificationPolicy.FULL_SCAN],
)
def test_out_of_bounds_spelling_stringify_passes_structural_and_full_scan(
    verification_policy: VerificationPolicy,
) -> None:
    table = TableCatalog(
        "records",
        (
            ColumnCatalog("id", "INT", False, 1),
            ColumnCatalog("flags", "BIT(65)", True, None),
        ),
        1,
    )

    class OutOfBoundsProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return (table,)

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return self.read_catalog(candidate)

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            yield record_batch(table, [(1, "0x01")], UnknownTypePolicy.STRINGIFY)

    manifest = manifest_from_tables((table,))

    result = verify_import_candidate(
        cast(VersionedImportProvider, OutOfBoundsProvider()),
        candidate="candidate",
        manifest=manifest,
        verification_policy=verification_policy,
        unknown_type_policy=UnknownTypePolicy.STRINGIFY,
    )
    assert result == ImportVerificationResult(
        completed_verification_policy=verification_policy,
        unknown_type_policy=UnknownTypePolicy.STRINGIFY,
    )
    if verification_policy == VerificationPolicy.FULL_SCAN:
        batch = next(
            OutOfBoundsProvider().stream_table(
                "candidate",
                table,
                UnknownTypePolicy.STRINGIFY,
            )
        )
        assert batch.column("flags").to_pylist() == ["0x01"]


def test_full_scan_sql_value_conversion_error_maps_to_verification_failed() -> None:
    class ConversionFailureProvider:
        def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1),)

        def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
            return self.read_catalog(candidate)

        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            raise SqlValueConversionError(table="records", column="id", sql_type="INT")
            yield pa.record_batch({"id": pa.array([1], type=pa.int32())})

    table = TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 1)
    manifest = manifest_from_tables((table,))

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            cast(VersionedImportProvider, ConversionFailureProvider()),
            candidate="candidate",
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
    assert exc_info.value.detail == "value conversion failed for records.id"


@pytest.mark.integration
def test_full_scan_zero_date_conversion_failure(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
) -> None:
    sql = """
CREATE TABLE zero_dates (id INT NOT NULL PRIMARY KEY, event_date DATE NULL);
INSERT INTO zero_dates VALUES (1, '0000-00-00');
"""
    staging_path = _write_staging_sql(import_layout, "zero-dates.sql", sql)
    try:
        candidate = _candidate_from_replay(import_provider, import_layout, staging_path)
    except ImportProviderError:
        pytest.skip("Dolt/sql_mode rejected zero-date insert for zero_dates fixture")
    catalog = import_provider.read_catalog(candidate)
    table = catalog[0]
    manifest = manifest_from_tables((table,))

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.FULL_SCAN,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
    assert "value conversion failed" in (exc_info.value.detail or "")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("catalog_tables", "manifest_tables", "expected_detail"),
    [
        (
            (
                TableCatalog("extra", (ColumnCatalog("id", "INT", False, 1),), 0),
                TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 0),
            ),
            (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 0),),
            "table extra not present in manifest",
        ),
        (
            (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 0),),
            (),
            "table records not present in manifest",
        ),
        (
            (),
            (TableCatalog("records", (ColumnCatalog("id", "INT", False, 1),), 0),),
            "table records not present in catalog",
        ),
    ],
)
def test_full_scan_catalog_manifest_mismatch_raises_typed_error(
    catalog_tables: tuple[TableCatalog, ...],
    manifest_tables: tuple[TableCatalog, ...],
    expected_detail: str | None,
) -> None:
    from gateway_repository_service.versioned_import.verification import _full_scan_tables

    class ScanProvider:
        def stream_table(self, *_args: object, **_kwargs: object) -> Iterator[pa.RecordBatch]:
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})

    manifest = manifest_from_tables(manifest_tables)
    with pytest.raises(ImportVerificationError) as exc_info:
        _full_scan_tables(
            cast(VersionedImportProvider, ScanProvider()),
            candidate="candidate",
            catalog=catalog_tables,
            manifest=manifest,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE
    if expected_detail is not None:
        assert expected_detail in (exc_info.value.detail or "")
