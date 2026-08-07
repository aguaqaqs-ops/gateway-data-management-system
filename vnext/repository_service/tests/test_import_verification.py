"""Tests for Versioned import candidate verification."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog
from gateway_repository_service.fixtures import Workload, generate_fixture
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
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
from support.lifecycle_harness import dolt_available, lifecycle_settings

OPERATION_ID = UUID("00000000-0000-4000-8000-0000000000b1")


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
            UnknownTypePolicy.STRINGIFY,
            "with_unknown",
            "exact",
            None,
            id="full-scan-stringify-scans-rows",
        ),
    ],
)
@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
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

    if catalog_kind == "known_only":
        base_tables = _tables_without_unknown(fixture.expected_tables)
    else:
        base_tables = tuple(
            next(table for table in catalog if table.name == expected.name)
            for expected in fixture.expected_tables
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
            _assert_stringify_metadata(import_provider, candidate, catalog)
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


def _assert_stringify_metadata(
    provider: CandidateAImportProvider,
    candidate: str,
    catalog: tuple[TableCatalog, ...],
) -> None:
    unknown_table = next(table for table in catalog if table.name == "unknown_types")
    batches = list(
        provider.stream_table(candidate, unknown_table, UnknownTypePolicy.STRINGIFY)
    )
    assert batches
    batch = batches[0]
    field = batch.schema.field("unknown_value")
    assert pa.types.is_large_string(field.type)
    assert field.nullable is True
    metadata = field.metadata or {}
    assert metadata.get(b"gateway.sql_type") == b"ENUM('A','B')"
    assert metadata.get(b"gateway.lossy") == b"true"
    values = batch.column("unknown_value").to_pylist()
    assert values == ["a", None]


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_structural_mismatch_raises_verification_failed(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    candidate = _candidate_from_replay(import_provider, import_layout, fixture.replay_sql)
    catalog = import_provider.read_catalog(candidate)
    known_tables = _tables_without_unknown(
        tuple(next(table for table in catalog if table.name == expected.name) for expected in fixture.expected_tables)
    )
    manifest = manifest_from_tables(known_tables)

    with pytest.raises(ImportVerificationError) as exc_info:
        verify_import_candidate(
            import_provider,
            candidate=candidate,
            manifest=manifest,
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.STRINGIFY,
        )
    assert exc_info.value.code == VERIFICATION_FAILED_NOT_PUBLISHED_CODE


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_full_scan_row_count_mismatch_raises(
    import_provider: CandidateAImportProvider,
    import_layout: DurableLayout,
    tmp_path: Path,
) -> None:
    fixture = generate_fixture(tmp_path / "fixture", Workload.W0)
    candidate = _candidate_from_replay(import_provider, import_layout, fixture.replay_sql)
    catalog = import_provider.read_catalog(candidate)
    base_tables = tuple(
        next(table for table in catalog if table.name == expected.name)
        for expected in fixture.expected_tables
    )
    manifest = _wrong_row_count_manifest(
        manifest_from_tables(base_tables),
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
