"""Business composition of SQL Snapshot tables with composite_signal_point."""

from __future__ import annotations

import dataclasses
import secrets
from datetime import UTC, datetime

from gateway_shared_kernel import (
    DeclaredType,
    DeclaredTypeKind,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
)

from gateway_backend.capabilities.composite_signal.contracts import (
    COMPOSITE_SIGNAL_CONTRACT_VERSION,
    COMPOSITE_SIGNAL_POINT_KEY,
    COMPOSITE_SIGNAL_POINT_TABLE,
    CompositeDiagnosticCode,
    CompositeSignalPointRow,
    CompositeSignalRequest,
    CompositeSignalResult,
    CompositeSignalStatus,
    materialize_composite_signal,
)
from gateway_backend.capabilities.snapshot_materialization._catalog import (
    CatalogError,
    extract_special_device_catalog,
)
from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    fast_row_digest_of,
    fast_row_hash,
    raw_content_digest_of,
    raw_state_digest_of,
    row_content_hash,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    artifact_error_diagnostic,
    publish_ready_tables,
    require_artifact_store,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
    BusinessSnapshotMaterializationRequest,
    CacheTrustLevel,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    Snapshot,
    SnapshotColumnDescriptor,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    SourceKind,
    SqlSnapshotMaterializationRequest,
)
from gateway_backend.capabilities.snapshot_materialization.materialize import materialize_sql_snapshot
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_VERSION,
    MaterializedTableReader,
    ParseStatus,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
    SqlLogicalType,
)

_BIGINT = DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=64)
_TEXT = DeclaredType(kind=DeclaredTypeKind.STRING)
_DERIVED_COLUMNS = (
    ("source_table", "TEXT", _TEXT, False),
    ("point_gid", "BIGINT", _BIGINT, False),
    ("dev_addr", "BIGINT", _BIGINT, False),
    ("device_gid", "BIGINT", _BIGINT, False),
    ("point_name", "TEXT", _TEXT, False),
    ("point_payload_json", "LONGTEXT", _TEXT, False),
    ("formula_digest", "TEXT", _TEXT, True),
    ("formula_ast_json", "LONGTEXT", _TEXT, True),
)


def materialize_business_snapshot(
    request: BusinessSnapshotMaterializationRequest,
) -> SnapshotMaterializationResult:
    if type(request) is not BusinessSnapshotMaterializationRequest:
        raise ValueError("request must be BusinessSnapshotMaterializationRequest")
    stage = request.sql.materialization_stage
    trust = (
        CacheTrustLevel.PROVISIONAL
        if stage is MaterializationStage.PROVISIONAL
        else CacheTrustLevel.CONTENT_VERIFIED
    )
    if request.sql.policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
        try:
            require_artifact_store(request.sql.artifact_store)
        except ArtifactPublishError as exc:
            return _failed(stage, trust, (artifact_error_diagnostic(exc),))
    if request.xml is not None and request.xml.status is ParseStatus.FAILED:
        return _failed(
            stage,
            trust,
            (
                _error(
                    MaterializationDiagnosticCode.XML_DOCUMENT_FAILED,
                    "XML document result is FAILED",
                ),
            ),
        )
    sql_result = materialize_sql_snapshot(_sql_with_readers(request.sql))
    if sql_result.status is SnapshotMaterializationStatus.FAILED:
        return sql_result
    summary = sql_result.summary
    if summary is None:
        return _failed(
            stage,
            trust,
            (
                _error(
                    MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                    "SQL materialization did not publish a summary",
                ),
            ),
        )
    try:
        catalog = extract_special_device_catalog(sql_result)
    except CatalogError as exc:
        return _failed(
            stage,
            trust,
            (
                _error(
                    MaterializationDiagnosticCode.COMPOSITE_CATALOG_UNAVAILABLE,
                    exc.message,
                    table=exc.table,
                ),
            ),
        )
    if any(table.table_name == COMPOSITE_SIGNAL_POINT_TABLE for table in summary.tables):
        return _failed(
            stage,
            trust,
            (
                _error(
                    MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED,
                    "SQL tables already contain composite_signal_point",
                    table=COMPOSITE_SIGNAL_POINT_TABLE,
                ),
            ),
        )
    composite = materialize_composite_signal(
        CompositeSignalRequest(
            logic=request.logic,
            catalog=catalog,
            context=request.sql.context,
            xml=request.xml,
        )
    )
    if composite.status is CompositeSignalStatus.FAILED:
        return _failed(stage, trust, _map_composite_diagnostics(composite))
    try:
        composed = _compose(request, sql_result, composite, stage, trust)
        if request.sql.policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
            return _with_artifacts(composed, request)
        return composed
    except ArtifactPublishError as exc:
        return _failed(stage, trust, (artifact_error_diagnostic(exc),))


def _sql_with_readers(sql: SqlSnapshotMaterializationRequest) -> SqlSnapshotMaterializationRequest:
    if sql.policy is MaterializationPolicy.READERS_REQUIRED:
        return sql
    return dataclasses.replace(sql, policy=MaterializationPolicy.READERS_REQUIRED)


def _compose(
    request: BusinessSnapshotMaterializationRequest,
    sql_result: SnapshotMaterializationResult,
    composite: CompositeSignalResult,
    stage: MaterializationStage,
    trust: CacheTrustLevel,
) -> SnapshotMaterializationResult:
    if sql_result.snapshot is None or sql_result.summary is None or sql_result.table_set is None:
        return _failed(
            stage,
            trust,
            (
                _error(
                    MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                    "SQL materialization did not publish readers required for composition",
                ),
            ),
        )
    derived_descriptor, derived_table = _derived_table(
        composite.rows,
        stage,
        request.sql.table_ruleset_version,
        request.sql.policy,
    )
    tables = (*sql_result.summary.tables, derived_descriptor)
    snapshot_id = secrets.token_hex(16)
    source_context = SnapshotSourceContext(
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        sql_source_digest=request.sql.sql_source_digest,
        composite_logic_source_digest=request.logic.composite_logic_source_digest,
    )
    snapshot_digest = snapshot_digest_of(
        stage=stage,
        parser_version=PARSER_VERSION,
        table_ruleset_version=request.sql.table_ruleset_version,
        tables=tables,
        composite_logic_source_digest=request.logic.composite_logic_source_digest,
        composite_signal_contract_version=COMPOSITE_SIGNAL_CONTRACT_VERSION,
    )
    raw_state = raw_state_digest_of(tables)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        parser_version=PARSER_VERSION,
        table_ruleset_version=request.sql.table_ruleset_version,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        snapshot_materialization_contract_version=SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        materialization_stage=stage,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_context=source_context,
    )
    summary = SnapshotSummary(
        snapshot_id=snapshot_id,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state,
        materialization_stage=stage,
        parser_version=PARSER_VERSION,
        table_ruleset_version=request.sql.table_ruleset_version,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        table_count=len(tables),
        tables=tables,
        source_context=source_context,
        diagnostics=sql_result.diagnostics,
        row_count_total=sum(item.row_count for item in tables),
    )
    table_set: SnapshotTableSet | None = None
    if request.sql.policy in {
        MaterializationPolicy.READERS_REQUIRED,
        MaterializationPolicy.ARTIFACTS_REQUIRED,
    }:
        table_set = SnapshotTableSet(
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            table_ruleset_version=request.sql.table_ruleset_version,
            tables=(*sql_result.table_set.tables, derived_table),
            diagnostics=sql_result.diagnostics,
        )
    return SnapshotMaterializationResult(
        status=sql_result.status,
        materialization_stage=stage,
        cache_trust_level=trust,
        diagnostics=sql_result.diagnostics,
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
    )


def _derived_table(
    rows: tuple[CompositeSignalPointRow, ...],
    stage: MaterializationStage,
    table_ruleset_version: int,
    policy: MaterializationPolicy,
) -> tuple[SnapshotTableDescriptor, SnapshotTable]:
    source_columns = tuple(
        SourceColumnDescriptor(
            display_name=name,
            canonical_name=name,
            ordinal=index,
            sql_type=sql_type,
            logical_type=SqlLogicalType.STANDARD,
            declared_type=declared,
            nullable=nullable,
        )
        for index, (name, sql_type, declared, nullable) in enumerate(_DERIVED_COLUMNS)
    )
    source_descriptor = SourceTableDescriptor(
        display_name=COMPOSITE_SIGNAL_POINT_TABLE,
        canonical_name=COMPOSITE_SIGNAL_POINT_TABLE,
        columns=source_columns,
        primary_key_canonical_names=COMPOSITE_SIGNAL_POINT_KEY,
        reader_ready=True,
    )
    encoded_rows = tuple(_encode_row(row) for row in rows)
    row_hashes = tuple(row_content_hash(source_columns, row) for row in encoded_rows)
    fast_hashes = tuple(fast_row_hash(source_columns, row) for row in encoded_rows)
    compare_keys = COMPOSITE_SIGNAL_POINT_KEY
    schema_digest = compare_schema_digest(
        COMPOSITE_SIGNAL_POINT_TABLE,
        tuple(column.canonical_name for column in source_columns),
        compare_keys,
    )
    descriptor = SnapshotTableDescriptor(
        table_name=COMPOSITE_SIGNAL_POINT_TABLE,
        display_table_name=COMPOSITE_SIGNAL_POINT_TABLE,
        columns=tuple(
            SnapshotColumnDescriptor(
                name=column.canonical_name,
                display_name=column.display_name,
                nullable=column.nullable,
                scalar_type=column.sql_type,
            )
            for column in source_columns
        ),
        primary_key_columns=COMPOSITE_SIGNAL_POINT_KEY,
        compare_key_columns=compare_keys,
        row_count=len(encoded_rows),
        materialization_stage=stage,
        compare_schema_digest=schema_digest,
        table_ruleset_version=table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        fast_row_digest=fast_row_digest_of(fast_hashes),
        raw_content_digest=(
            raw_content_digest_of(row_hashes) if stage is MaterializationStage.FINAL else None
        ),
    )
    reader = None
    if policy in {
        MaterializationPolicy.READERS_REQUIRED,
        MaterializationPolicy.ARTIFACTS_REQUIRED,
    }:
        source = MaterializedTableReader(source_descriptor, encoded_rows)
        reader = BoundSnapshotTableReader(descriptor, source)
    return descriptor, SnapshotTable(descriptor=descriptor, reader=reader)


def _encode_row(row: CompositeSignalPointRow) -> SourceRow:
    formula_digest: NullScalar | StringScalar
    formula_ast: NullScalar | StringScalar
    if row.formula_digest is None:
        formula_digest = NullScalar()
        formula_ast = NullScalar()
    else:
        formula_digest = StringScalar(row.formula_digest)
        formula_ast = StringScalar(row.formula_ast_json or "")
    return (
        StringScalar(row.source_table),
        SignedIntegerScalar(str(row.point_gid)),
        SignedIntegerScalar(str(row.dev_addr)),
        SignedIntegerScalar(str(row.device_gid)),
        StringScalar(row.point_name),
        StringScalar(row.point_payload_json),
        formula_digest,
        formula_ast,
    )


def _map_composite_diagnostics(
    result: CompositeSignalResult,
) -> tuple[MaterializationDiagnostic, ...]:
    mapped: list[MaterializationDiagnostic] = []
    for item in result.diagnostics:
        mapped.append(_error(_map_code(item.code), item.message, table=item.table))
    return tuple(mapped)


def _map_code(code: CompositeDiagnosticCode) -> MaterializationDiagnosticCode:
    if code is CompositeDiagnosticCode.XML_DOCUMENT_FAILED:
        return MaterializationDiagnosticCode.XML_DOCUMENT_FAILED
    if code is CompositeDiagnosticCode.MATERIALIZATION_CANCELLED:
        return MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED
    if code is CompositeDiagnosticCode.MATERIALIZATION_TIMEOUT:
        return MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT
    if code is CompositeDiagnosticCode.CATALOG_UNAVAILABLE:
        return MaterializationDiagnosticCode.COMPOSITE_CATALOG_UNAVAILABLE
    return MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED


def _failed(
    stage: MaterializationStage,
    trust: CacheTrustLevel,
    diagnostics: tuple[MaterializationDiagnostic, ...],
) -> SnapshotMaterializationResult:
    return SnapshotMaterializationResult(
        status=SnapshotMaterializationStatus.FAILED,
        materialization_stage=stage,
        cache_trust_level=trust,
        diagnostics=diagnostics,
    )


def _error(
    code: MaterializationDiagnosticCode,
    message: str,
    *,
    table: str | None = None,
) -> MaterializationDiagnostic:
    return MaterializationDiagnostic(
        code=code,
        severity=DiagnosticSeverity.ERROR,
        message=message,
        table=table,
    )


def _with_artifacts(
    result: SnapshotMaterializationResult,
    request: BusinessSnapshotMaterializationRequest,
) -> SnapshotMaterializationResult:
    if (
        result.status is SnapshotMaterializationStatus.FAILED
        or result.snapshot is None
        or result.table_set is None
    ):
        return result
    store = require_artifact_store(request.sql.artifact_store)
    published = publish_ready_tables(
        result.table_set.tables,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=request.sql.context,
    )
    table_set = SnapshotTableSet(
        snapshot_id=result.table_set.snapshot_id,
        snapshot_digest=result.table_set.snapshot_digest,
        table_ruleset_version=result.table_set.table_ruleset_version,
        tables=published,
        diagnostics=result.table_set.diagnostics,
    )
    return SnapshotMaterializationResult(
        status=result.status,
        materialization_stage=result.materialization_stage,
        cache_trust_level=result.cache_trust_level,
        diagnostics=result.diagnostics,
        snapshot=result.snapshot,
        summary=result.summary,
        table_set=table_set,
    )
