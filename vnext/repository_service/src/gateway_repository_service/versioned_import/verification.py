"""Verification engine for immutable Versioned import candidates.

NONE + STRINGIFY returns immediately without provider calls (§12 literal).
"""

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    CompiledTablePlan,
    SqlValueConversionError,
    TableCatalog,
    UnknownSqlTypeError,
    arrow_type,
    compile_table_plan,
    is_known_sql_type,
)
from gateway_repository_service.versioned_import.models import ImportManifest, ImportManifestTable
from gateway_repository_service.versioned_import.ports import VersionedImportProvider

IMPORT_REJECTED_CODE = "IMPORT_REJECTED"
VERIFICATION_FAILED_NOT_PUBLISHED_CODE = "VERIFICATION_FAILED_NOT_PUBLISHED"


@dataclass(frozen=True, slots=True)
class ImportVerificationResult:
    completed_verification_policy: VerificationPolicy
    unknown_type_policy: UnknownTypePolicy


class ImportVerificationError(Exception):
    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail or code)


def verify_import_candidate(
    provider: VersionedImportProvider,
    *,
    candidate: str,
    manifest: ImportManifest,
    verification_policy: VerificationPolicy,
    unknown_type_policy: UnknownTypePolicy,
) -> ImportVerificationResult:
    if (
        verification_policy == VerificationPolicy.NONE
        and unknown_type_policy == UnknownTypePolicy.STRINGIFY
    ):
        return ImportVerificationResult(
            completed_verification_policy=verification_policy,
            unknown_type_policy=unknown_type_policy,
        )

    if (
        verification_policy == VerificationPolicy.NONE
        and unknown_type_policy == UnknownTypePolicy.REJECT
    ):
        catalog = provider.read_type_catalog(candidate)
        _reject_unknown_catalog_types(catalog)
        return ImportVerificationResult(
            completed_verification_policy=verification_policy,
            unknown_type_policy=unknown_type_policy,
        )

    catalog = provider.read_catalog(candidate)

    if unknown_type_policy == UnknownTypePolicy.REJECT:
        _reject_unknown_catalog_types(catalog)

    if verification_policy in {
        VerificationPolicy.STRUCTURAL,
        VerificationPolicy.FULL_SCAN,
    }:
        _assert_columns_mappable(catalog, unknown_type_policy)
        _compare_manifest_structural(manifest, catalog)

    if verification_policy == VerificationPolicy.FULL_SCAN:
        _full_scan_tables(provider, candidate, catalog, manifest, unknown_type_policy)

    return ImportVerificationResult(
        completed_verification_policy=verification_policy,
        unknown_type_policy=unknown_type_policy,
    )


def _manifest_tables_as_catalog(manifest: ImportManifest) -> tuple[TableCatalog, ...]:
    tables: list[TableCatalog] = []
    for table in manifest.tables:
        tables.append(_manifest_table_as_catalog(table))
    return tuple(tables)


def _manifest_table_as_catalog(table: ImportManifestTable) -> TableCatalog:
    pk_positions = {
        name: index for index, name in enumerate(table.table_schema.primary_key, start=1)
    }
    columns = tuple(
        ColumnCatalog(
            name=column.name,
            sql_type=column.sql_type,
            nullable=column.nullable,
            primary_key_position=pk_positions.get(column.name),
        )
        for column in table.table_schema.columns
    )
    return TableCatalog(name=table.name, columns=columns, row_count=table.row_count)


def _reject_unknown_catalog_types(catalog: tuple[TableCatalog, ...]) -> None:
    for table in catalog:
        for column in table.columns:
            if not is_known_sql_type(column.sql_type):
                raise ImportVerificationError(
                    IMPORT_REJECTED_CODE,
                    detail=f"unknown SQL type in catalog: {table.name}.{column.name}",
                )


def _assert_columns_mappable(
    catalog: tuple[TableCatalog, ...],
    unknown_type_policy: UnknownTypePolicy,
) -> None:
    """Fail fast when catalog spellings cannot be mapped to Arrow.

    Under REJECT this is redundant with ``_reject_unknown_catalog_types`` because
    both use ``arrow_type(..., REJECT)``. Under STRINGIFY malformed temporal
    spellings are already rejected during ``normalize_sql_type``. STRUCTURAL and
    FULL_SCAN alignment for unknown values is enforced in ``convert_value``.
    """
    for table in catalog:
        for column in table.columns:
            try:
                arrow_type(column.sql_type, unknown_type_policy)
            except UnknownSqlTypeError as exc:
                raise ImportVerificationError(
                    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                    detail=f"unmappable SQL type in catalog: {table.name}.{column.name}",
                ) from exc


def _compare_manifest_structural(
    manifest: ImportManifest,
    catalog: tuple[TableCatalog, ...],
) -> None:
    expected = _manifest_tables_as_catalog(manifest)
    if len(catalog) != len(expected):
        raise ImportVerificationError(
            VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
            detail="user table set mismatch",
        )
    for actual_table, expected_table in zip(catalog, expected, strict=True):
        if actual_table.name != expected_table.name:
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail="table order/name mismatch",
            )
        if actual_table.row_count != expected_table.row_count:
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"row count mismatch for {actual_table.name}",
            )
        if actual_table.primary_key != expected_table.primary_key:
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"primary key mismatch for {actual_table.name}",
            )
        if len(actual_table.columns) != len(expected_table.columns):
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"column count mismatch for {actual_table.name}",
            )
        for actual_column, expected_column in zip(
            actual_table.columns,
            expected_table.columns,
            strict=True,
        ):
            if (
                actual_column.name != expected_column.name
                or actual_column.sql_type != expected_column.sql_type
                or actual_column.nullable != expected_column.nullable
                or actual_column.primary_key_position != expected_column.primary_key_position
            ):
                raise ImportVerificationError(
                    VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                    detail=(
                        f"column mismatch for {actual_table.name}.{expected_column.name}"
                    ),
                )


def _full_scan_tables(
    provider: VersionedImportProvider,
    candidate: str,
    catalog: tuple[TableCatalog, ...],
    manifest: ImportManifest,
    unknown_type_policy: UnknownTypePolicy,
) -> None:
    # FULL_SCAN enforces bidirectional manifest/catalog table-name alignment without
    # assuming _compare_manifest_structural() already ran.
    manifest_names = {table.name for table in manifest.tables}
    catalog_names = {table.name for table in catalog}
    for table_name in sorted(catalog_names - manifest_names):
        raise ImportVerificationError(
            VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
            detail=f"table {table_name} not present in manifest",
        )
    for table_name in sorted(manifest_names - catalog_names):
        raise ImportVerificationError(
            VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
            detail=f"table {table_name} not present in catalog",
        )
    manifest_row_counts = {table.name: table.row_count for table in manifest.tables}
    for table in catalog:
        expected_row_count = manifest_row_counts[table.name]
        scanned_rows = 0
        plan = compile_table_plan(table, unknown_type_policy)
        try:
            for batch in provider.stream_table(candidate, table, unknown_type_policy):
                _assert_batch_contract(batch, plan)
                scanned_rows += batch.num_rows
        except SqlValueConversionError as exc:
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"value conversion failed for {table.name}.{exc.column}",
            ) from exc
        if scanned_rows != expected_row_count:
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"scanned row count mismatch for {table.name}",
            )


def _assert_batch_contract(
    batch: pa.RecordBatch,
    plan: CompiledTablePlan,
) -> None:
    table = plan.catalog
    if batch.num_columns != len(table.columns):
        raise ImportVerificationError(
            VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
            detail=f"Arrow column count mismatch for {table.name}",
        )
    for index, column in enumerate(table.columns):
        field = batch.schema.field(index)
        expected_field = plan.expected_schema.field(index)
        if (
            field.name != column.name
            or field.type != expected_field.type
            or field.nullable != column.nullable
            or (field.metadata or {}) != (expected_field.metadata or {})
        ):
            raise ImportVerificationError(
                VERIFICATION_FAILED_NOT_PUBLISHED_CODE,
                detail=f"Arrow field contract mismatch for {table.name}.{column.name}",
            )
