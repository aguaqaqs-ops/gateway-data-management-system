from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...core.row_digests import stable_snapshot_rows_digest
from ...core.scalar_encoding import normalize_snapshot_rows
from ...repository_server.catalog import (
    RepositoryTableCatalog,
    RepositoryTableCatalogTable,
    catalog_digest,
)
from ...repository_server.ref_session import (
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    RepositoryTableAccessProvider,
)
from ..table_rules import TableRuleRegistry, default_table_rule_registry
from .canonical_storage import logical_to_physical_table_map
from .hidden_summary import (
    HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME,
    read_hidden_summary_snapshot,
)
from .models import (
    ROW_MATERIALIZATION_PROFILE,
    SNAPSHOT_DIGEST_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SNAPSHOT_SUMMARY_SCHEMA_VERSION,
    SQL_PARSER_VERSION,
    SnapshotMaterializationStage,
    TABLE_RULESET_VERSION,
    Snapshot,
    SnapshotMaterializationResult,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableColumn,
    SnapshotTableDescriptor,
    SnapshotTableSet,
)
from .readers import InMemorySnapshotTableReader


IMMUTABLE_REPOSITORY_REF_SOURCE_KIND = "IMMUTABLE_REPOSITORY_REF"


@dataclass(frozen=True, slots=True)
class RepositoryRefMaterializationInput:
    repository_ref: RepositoryRef
    repository_table_access_provider: RepositoryTableAccessProvider
    digest_contract_version: str = SNAPSHOT_DIGEST_CONTRACT_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    snapshot_materialization_contract_version: str = (
        SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
    )
    parser_version: str = SQL_PARSER_VERSION
    summary_contract_version: str = SNAPSHOT_SUMMARY_SCHEMA_VERSION
    row_materialization_profile: str = ROW_MATERIALIZATION_PROFILE
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    materialization_policy: str = "READERS_REQUIRED"
    cache_policy: str = "DISABLED"
    timeout_policy: RepositoryRefTimeoutPolicy | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repository_ref, RepositoryRef):
            raise TypeError("repository_ref must be a RepositoryRef")
        if not isinstance(self.repository_table_access_provider, RepositoryTableAccessProvider):
            raise TypeError(
                "repository_table_access_provider must implement RepositoryTableAccessProvider"
            )
        for field_name in (
            "digest_contract_version",
            "table_ruleset_version",
            "scalar_encoding_version",
            "snapshot_materialization_contract_version",
            "parser_version",
            "summary_contract_version",
            "row_materialization_profile",
            "materialization_policy",
            "cache_policy",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.timeout_policy is not None and not isinstance(
            self.timeout_policy,
            RepositoryRefTimeoutPolicy,
        ):
            raise TypeError("timeout_policy must be a RepositoryRefTimeoutPolicy or None")

        normalized_requested_tables: list[str] = []
        seen_tables: set[str] = set()
        for table_name in self.requested_tables:
            canonical_name = canonical_identifier(table_name)
            if not canonical_name or canonical_name in seen_tables:
                continue
            seen_tables.add(canonical_name)
            normalized_requested_tables.append(canonical_name)
        object.__setattr__(self, "requested_tables", tuple(normalized_requested_tables))


def materialize_repository_ref(
    materialization_input: RepositoryRefMaterializationInput,
) -> SnapshotMaterializationResult:
    table_rule_registry = default_table_rule_registry()
    session = materialization_input.repository_table_access_provider.open_ref(
        materialization_input.repository_ref,
        materialization_input.timeout_policy,
    )
    diagnostics: list[DiagnosticRecord] = []
    try:
        return _materialize_repository_ref_from_summary(
            materialization_input=materialization_input,
            session=session,
            table_rule_registry=table_rule_registry,
            diagnostics=diagnostics,
        )
    finally:
        session.close()


def _index_catalog_tables(
    catalog: RepositoryTableCatalog,
) -> dict[str, RepositoryTableCatalogTable]:
    indexed: dict[str, RepositoryTableCatalogTable] = {}
    for table in catalog.tables.values():
        canonical_name = canonical_identifier(table.table_name)
        if canonical_name == HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME:
            continue
        if canonical_name in indexed:
            raise ValueError("repository table name collision after canonicalization")
        indexed[canonical_name] = table
    return indexed


def _business_catalog_digest(catalog: RepositoryTableCatalog) -> DigestRef:
    business_tables = {
        table_name: table
        for table_name, table in catalog.tables.items()
        if canonical_identifier(table_name) != HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME
    }
    business_catalog = RepositoryTableCatalog(
        repository_id=catalog.repository_id,
        repository_ref=catalog.repository_ref,
        resolved_commit_hash=catalog.resolved_commit_hash,
        repository_server_contract_version=catalog.repository_server_contract_version,
        tables=business_tables,
        dolt_version=catalog.dolt_version,
        diagnostics=catalog.diagnostics,
    )
    return catalog_digest(business_catalog)


def _materialize_catalog_table(
    *,
    session,
    catalog_table: RepositoryTableCatalogTable,
    source_digest: DigestRef,
    materialization_input: RepositoryRefMaterializationInput,
    table_rule_registry: TableRuleRegistry,
    expected_descriptor: SnapshotTableDescriptor | None = None,
    allow_physical_alias: bool = False,
) -> tuple[SnapshotTableDescriptor, SnapshotTable]:
    reader = session.open_table_reader(catalog_table.table_name)
    try:
        raw_rows = tuple(tuple(row) for row in reader.stream_rows())
    finally:
        reader.close()

    snapshot_columns = tuple(
        SnapshotTableColumn(
            name=column.name,
            display_name=column.display_name,
            scalar_type=column.scalar_type,
            nullable=column.nullable,
        )
        for column in catalog_table.columns
    )
    digest_columns = (
        expected_descriptor.columns if expected_descriptor is not None else snapshot_columns
    )
    digest_row_values = _align_rows_to_columns(
        raw_rows,
        source_columns=snapshot_columns,
        target_columns=digest_columns,
    )
    rows = normalize_snapshot_rows(digest_row_values, digest_columns)
    semantic_decision = table_rule_registry.resolve_table_semantics(
        catalog_table.table_name,
        primary_key_columns=tuple(catalog_table.primary_key_columns),
    )
    compare_schema_digest = DigestRef.from_payload(
        {
            "table_name": canonical_identifier(catalog_table.table_name),
            "columns": sorted(column.name for column in snapshot_columns),
            "compare_key_columns": sorted(semantic_decision.compare_key_columns),
            "table_ruleset_version": materialization_input.table_ruleset_version,
            "scalar_encoding_version": materialization_input.scalar_encoding_version,
            "row_materialization_profile": materialization_input.row_materialization_profile,
        }
    )
    raw_create_sql = _render_repository_table_create_sql(catalog_table)
    source_ddl_digest = DigestRef.from_bytes(raw_create_sql.encode("utf-8"))
    raw_content_digest = stable_snapshot_rows_digest(digest_row_values, digest_columns)
    descriptor = SnapshotTableDescriptor(
        table_name=canonical_identifier(catalog_table.table_name),
        display_table_name=catalog_table.display_table_name,
        table_role=semantic_decision.static_role.value,
        columns=snapshot_columns,
        compare_key_columns=semantic_decision.compare_key_columns,
        row_count=len(rows),
        source_ddl_digest=source_ddl_digest,
        table_raw_sql_digest=source_ddl_digest,
        base_table_fingerprint=source_ddl_digest,
        compare_schema_digest=compare_schema_digest,
        raw_content_digest=raw_content_digest,
        business_content_digest=raw_content_digest,
        table_ruleset_version=materialization_input.table_ruleset_version,
        row_materialization_profile=materialization_input.row_materialization_profile,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
    )
    if expected_descriptor is not None:
        _validate_repository_ref_table_descriptor(
            expected_descriptor=expected_descriptor,
            actual_descriptor=descriptor,
            allow_physical_alias=allow_physical_alias,
        )
        descriptor = expected_descriptor
    table = SnapshotTable(
        descriptor=descriptor,
        reader=InMemorySnapshotTableReader(
            _descriptor=descriptor,
            _rows=rows,
        ),
        raw_create_sql=raw_create_sql,
    )
    return descriptor, table


def _align_rows_to_columns(
    rows: Sequence[Sequence[object]],
    *,
    source_columns: Sequence[SnapshotTableColumn],
    target_columns: Sequence[SnapshotTableColumn],
) -> tuple[tuple[object, ...], ...]:
    source_column_names = tuple(column.name for column in source_columns)
    target_column_names = tuple(column.name for column in target_columns)
    if source_column_names == target_column_names:
        return tuple(tuple(row) for row in rows)

    source_index_by_name = {
        column_name: index for index, column_name in enumerate(source_column_names)
    }
    missing_columns = [
        column_name
        for column_name in target_column_names
        if column_name not in source_index_by_name
    ]
    if missing_columns:
        raise ValueError(
            "repository catalog is missing expected summary column(s): "
            + ", ".join(sorted(missing_columns))
        )

    aligned_rows: list[tuple[object, ...]] = []
    for row_index, row in enumerate(rows):
        row_tuple = tuple(row)
        if len(row_tuple) != len(source_column_names):
            raise ValueError(
                f"repository row {row_index} has {len(row_tuple)} values but "
                f"catalog exposes {len(source_column_names)} columns"
            )
        aligned_rows.append(
            tuple(row_tuple[source_index_by_name[column_name]] for column_name in target_column_names)
        )
    return tuple(aligned_rows)


def read_repository_ref_summary_snapshot(
    materialization_input: RepositoryRefMaterializationInput,
) -> Snapshot:
    session = materialization_input.repository_table_access_provider.open_ref(
        materialization_input.repository_ref,
        materialization_input.timeout_policy,
    )
    try:
        catalog = session.get_catalog()
        source_digest = _business_catalog_digest(catalog)
        return _build_repository_ref_snapshot_from_summary(
            materialization_input=materialization_input,
            catalog=catalog,
            source_digest=source_digest,
            summary=read_hidden_summary_snapshot(session),
        )
    finally:
        session.close()


def _materialize_repository_ref_from_summary(
    *,
    materialization_input: RepositoryRefMaterializationInput,
    session,
    table_rule_registry: TableRuleRegistry,
    diagnostics: list[DiagnosticRecord],
) -> SnapshotMaterializationResult:
    catalog = session.get_catalog()
    source_digest = _business_catalog_digest(catalog)
    summary_snapshot = _build_repository_ref_snapshot_from_summary(
        materialization_input=materialization_input,
        catalog=catalog,
        source_digest=source_digest,
        summary=read_hidden_summary_snapshot(session),
    )
    catalog_tables = _index_catalog_tables(catalog)
    summary_tables = {
        descriptor.table_name: descriptor for descriptor in summary_snapshot.summary.tables
    }
    logical_to_physical = logical_to_physical_table_map(summary_snapshot.summary)
    required_physical_tables = set(logical_to_physical.values())
    requested_tables = tuple(materialization_input.requested_tables)
    requested_table_set = set(requested_tables)
    selected_table_names = tuple(
        sorted(requested_table_set) if requested_table_set else sorted(summary_tables)
    )
    missing_requested_tables = sorted(
        table_name for table_name in requested_table_set if table_name not in summary_tables
    )
    if missing_requested_tables:
        diagnostics.append(
            DiagnosticRecord(
                code="repository-ref.materialization.requested-table-missing",
                message="requested table(s) were not found in the repository summary",
                phase="materialization",
                severity="WARNING",
                details={"tables": missing_requested_tables},
            )
        )
    tables: dict[str, SnapshotTable] = {}
    selected_summary_tables: list[SnapshotTableDescriptor] = []
    for canonical_name in selected_table_names:
        summary_descriptor = summary_tables.get(canonical_name)
        if summary_descriptor is None:
            if not requested_table_set:
                raise ValueError(f"repository summary is missing table: {canonical_name}")
            continue
        physical_table_name = logical_to_physical.get(canonical_name, canonical_name)
        catalog_table = catalog_tables.get(physical_table_name)
        if catalog_table is None:
            if not requested_table_set:
                raise ValueError(f"repository catalog is missing table: {physical_table_name}")
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-ref.materialization.catalog-table-missing",
                    message="requested table is missing from the repository catalog",
                    phase="materialization",
                    severity="WARNING",
                    details={
                        "table_name": canonical_name,
                        "physical_table_name": physical_table_name,
                    },
                )
            )
            continue
        descriptor, snapshot_table = _materialize_catalog_table(
            session=session,
            catalog_table=catalog_table,
            source_digest=source_digest,
            materialization_input=materialization_input,
            table_rule_registry=table_rule_registry,
            expected_descriptor=summary_descriptor,
            allow_physical_alias=physical_table_name != canonical_name,
        )
        tables[descriptor.table_name] = snapshot_table
        selected_summary_tables.append(descriptor)

    if not requested_table_set:
        catalog_table_names = set(catalog_tables)
        if catalog_table_names != required_physical_tables:
            missing_from_catalog = sorted(required_physical_tables - catalog_table_names)
            extra_in_catalog = sorted(catalog_table_names - required_physical_tables)
            raise ValueError(
                "repository catalog and hidden snapshot summary do not describe the same physical tables"
                f" (missing_from_catalog={missing_from_catalog}, extra_in_catalog={extra_in_catalog})"
            )

    selected_summary_tables = sorted(
        selected_summary_tables,
        key=lambda descriptor: (descriptor.table_name.casefold(), descriptor.table_name),
    )
    descriptor_map = {descriptor.table_name: descriptor for descriptor in selected_summary_tables}
    tables = {
        table_name: replace(
            table,
            descriptor=descriptor_map[table_name],
            reader=replace(table.reader, _descriptor=descriptor_map[table_name]),
        )
        for table_name, table in tables.items()
    }
    selected_row_count_total = sum(descriptor.row_count for descriptor in selected_summary_tables)
    selected_raw_state_digest = DigestRef.from_payload(
        {
            "materialization_stage": SnapshotMaterializationStage.FINAL.value,
            "source_kind": IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
            "source_digest": source_digest.to_payload(),
            "table_count": len(selected_summary_tables),
            "row_count_total": selected_row_count_total,
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "row_count": descriptor.row_count,
                    "raw_content_digest": descriptor.raw_content_digest.to_payload(),
                }
                for descriptor in selected_summary_tables
            ],
        }
    )
    selected_snapshot_digest = DigestRef.from_payload(
        {
            "digest_contract_version": materialization_input.digest_contract_version,
            "materialization_stage": SnapshotMaterializationStage.FINAL.value,
            "source_kind": IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
            "source_digest": source_digest.to_payload(),
            "repository_id": materialization_input.repository_ref.repository_id,
            "repository_ref": materialization_input.repository_ref.repository_ref,
            "resolved_commit_hash": catalog.resolved_commit_hash,
            "repository_server_contract_version": catalog.repository_server_contract_version,
            "dolt_version": catalog.dolt_version,
            "parser_version": materialization_input.parser_version,
            "table_ruleset_version": materialization_input.table_ruleset_version,
            "scalar_encoding_version": materialization_input.scalar_encoding_version,
            "snapshot_materialization_contract_version": (
                materialization_input.snapshot_materialization_contract_version
            ),
            "row_materialization_profile": materialization_input.row_materialization_profile,
            "requested_tables": sorted(requested_table_set),
            "tables": [
                {
                    "table_name": descriptor.table_name,
                    "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
                    "raw_content_digest": descriptor.raw_content_digest.to_payload(),
                    "row_count": descriptor.row_count,
                }
                for descriptor in selected_summary_tables
            ],
        }
    )
    snapshot_id = f"snapshot:{selected_snapshot_digest.hex_digest}"
    source_context = SnapshotSourceContext(
        source_kind=IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
        source_digest=source_digest,
        repository_ref=materialization_input.repository_ref.repository_ref,
    )
    summary = replace(
        summary_snapshot.summary,
        snapshot_id=snapshot_id,
        snapshot_digest=selected_snapshot_digest,
        raw_state_digest=selected_raw_state_digest,
        business_state_digest=selected_raw_state_digest,
        table_count=len(selected_summary_tables),
        row_count_total=selected_row_count_total,
        tables=tuple(selected_summary_tables),
        missing_or_unsupported_tables=tuple(missing_requested_tables),
        source_context=source_context,
    )
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        source_kind=IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
        repository_id=materialization_input.repository_ref.repository_id,
        repository_ref=materialization_input.repository_ref.repository_ref,
        parser_version=materialization_input.parser_version,
        table_ruleset_version=materialization_input.table_ruleset_version,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
        snapshot_materialization_contract_version=(
            materialization_input.snapshot_materialization_contract_version
        ),
        row_materialization_profile=materialization_input.row_materialization_profile,
        materialization_stage=SnapshotMaterializationStage.FINAL.value,
        snapshot_digest=selected_snapshot_digest,
        raw_state_digest=selected_raw_state_digest,
        business_state_digest=selected_raw_state_digest,
        summary=summary,
        source_digest=source_digest,
        source_context=source_context,
        created_at=datetime.now(timezone.utc),
        diagnostics=tuple(diagnostics),
    )
    table_set = SnapshotTableSet(
        snapshot_id=snapshot_id,
        snapshot_digest=selected_snapshot_digest,
        table_ruleset_version=materialization_input.table_ruleset_version,
        tables=tables,
        resolution_plan=f"repository_ref:{materialization_input.materialization_policy}",
        diagnostics=tuple(diagnostics),
    )
    return SnapshotMaterializationResult(
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
        table_artifact_refs=None,
        materialization_input=None,
        cache_diagnostics=(),
        diagnostics=tuple(diagnostics),
    )


def _build_repository_ref_snapshot_from_summary(
    *,
    materialization_input: RepositoryRefMaterializationInput,
    catalog: RepositoryTableCatalog,
    source_digest: DigestRef,
    summary: SnapshotSummary,
) -> Snapshot:
    if summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        raise ValueError("hidden repository summary must be FINAL")
    if summary.summary_contract_version != materialization_input.summary_contract_version:
        raise ValueError("hidden repository summary contract version mismatch")
    if summary.parser_version != materialization_input.parser_version:
        raise ValueError("hidden repository summary parser version mismatch")
    if summary.table_ruleset_version != materialization_input.table_ruleset_version:
        raise ValueError("hidden repository summary table ruleset version mismatch")
    source_context = summary.source_context
    if source_context is None:
        raise ValueError("hidden repository summary is missing source_context")
    if source_context.source_digest is None:
        raise ValueError("hidden repository summary source digest is required")
    if source_context.repository_ref is not None and (
        canonical_identifier(source_context.repository_ref)
        != canonical_identifier(materialization_input.repository_ref.repository_ref)
    ):
        raise ValueError("hidden repository summary repository ref mismatch")
    normalized_source_context = replace(
        source_context,
        source_kind=IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
    )
    normalized_summary = replace(summary, source_context=normalized_source_context)
    return Snapshot(
        snapshot_id=normalized_summary.snapshot_id,
        source_kind=IMMUTABLE_REPOSITORY_REF_SOURCE_KIND,
        repository_id=materialization_input.repository_ref.repository_id,
        repository_ref=materialization_input.repository_ref.repository_ref,
        parser_version=materialization_input.parser_version,
        table_ruleset_version=materialization_input.table_ruleset_version,
        scalar_encoding_version=materialization_input.scalar_encoding_version,
        snapshot_materialization_contract_version=(
            materialization_input.snapshot_materialization_contract_version
        ),
        row_materialization_profile=materialization_input.row_materialization_profile,
        materialization_stage=normalized_summary.materialization_stage,
        snapshot_digest=normalized_summary.snapshot_digest,
        raw_state_digest=normalized_summary.raw_state_digest,
        business_state_digest=normalized_summary.business_state_digest,
        summary=normalized_summary,
        source_digest=normalized_source_context.source_digest,
        source_context=normalized_source_context,
        created_at=datetime.now(timezone.utc),
        diagnostics=tuple(),
    )


def _validate_repository_ref_table_descriptor(
    *,
    expected_descriptor: SnapshotTableDescriptor,
    actual_descriptor: SnapshotTableDescriptor,
    allow_physical_alias: bool = False,
) -> None:
    if not allow_physical_alias:
        if expected_descriptor.table_name != actual_descriptor.table_name:
            raise ValueError("repository summary table name mismatch")
        if expected_descriptor.display_table_name != actual_descriptor.display_table_name:
            raise ValueError("repository summary display table name mismatch")
    if expected_descriptor.table_role != actual_descriptor.table_role:
        raise ValueError("repository summary table role mismatch")
    expected_column_signature = tuple(
        (column.name, column.display_name, column.nullable)
        for column in expected_descriptor.columns
    )
    actual_column_signature = tuple(
        (column.name, column.display_name, column.nullable)
        for column in actual_descriptor.columns
    )
    if expected_column_signature != actual_column_signature:
        raise ValueError("repository summary columns mismatch")
    if expected_descriptor.compare_key_columns != actual_descriptor.compare_key_columns:
        raise ValueError("repository summary compare key columns mismatch")
    if expected_descriptor.row_count != actual_descriptor.row_count:
        raise ValueError("repository summary row count mismatch")
    if (
        not allow_physical_alias
        and expected_descriptor.compare_schema_digest != actual_descriptor.compare_schema_digest
    ):
        raise ValueError("repository summary compare schema digest mismatch")
    if expected_descriptor.raw_content_digest != actual_descriptor.raw_content_digest:
        raise ValueError("repository summary raw content digest mismatch")
    if expected_descriptor.business_content_digest != actual_descriptor.business_content_digest:
        raise ValueError("repository summary business content digest mismatch")
    if expected_descriptor.table_ruleset_version != actual_descriptor.table_ruleset_version:
        raise ValueError("repository summary table ruleset version mismatch")
    if expected_descriptor.row_materialization_profile != actual_descriptor.row_materialization_profile:
        raise ValueError("repository summary row materialization profile mismatch")
    if expected_descriptor.scalar_encoding_version != actual_descriptor.scalar_encoding_version:
        raise ValueError("repository summary scalar encoding version mismatch")


def _render_repository_table_create_sql(
    catalog_table: RepositoryTableCatalogTable,
) -> str:
    column_lines: list[str] = []
    for column in catalog_table.columns:
        column_type = column.scalar_type or column.raw_type or "TEXT"
        column_line = f"`{canonical_identifier(column.name)}` {column_type}"
        if column.nullable is False:
            column_line += " NOT NULL"
        elif column.nullable is True:
            column_line += " DEFAULT NULL"
        column_lines.append(column_line)
    if catalog_table.primary_key_columns:
        primary_key_columns = ", ".join(
            f"`{canonical_identifier(column_name)}`"
            for column_name in catalog_table.primary_key_columns
        )
        column_lines.append(f"PRIMARY KEY ({primary_key_columns})")
    return (
        f"CREATE TABLE `{canonical_identifier(catalog_table.table_name)}` (\n  "
        + ",\n  ".join(column_lines)
        + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8"
    )
