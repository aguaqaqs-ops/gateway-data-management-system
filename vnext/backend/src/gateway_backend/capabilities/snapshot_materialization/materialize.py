"""SQL Snapshot materializer. Consumes R2 ParseResult; does not invoke the SQL parser."""

from __future__ import annotations

import dataclasses
import secrets
import time
from datetime import UTC, datetime

from gateway_shared_kernel import CanonicalEncodingError, DigestRef, canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    encode_cell_frame,
    fast_row_digest_of,
    fast_row_hash,
    raw_content_digest_of,
    raw_state_digest_of,
    row_content_hash,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization._reader import (
    BoundSnapshotTableReader,
    as_reopenable,
)
from gateway_backend.capabilities.snapshot_materialization._ruleset import (
    CompareKeyError,
    compare_key_index,
    effective_key_columns,
)
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
    CacheTrustLevel,
    DegradedReason,
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
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_VERSION,
    ParsedTable,
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
    SourceTableDescriptor,
    TableAccessError,
    TableReader,
)
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableCompareKey,
)

_HaltCode = MaterializationDiagnosticCode


class _Halt(Exception):
    def __init__(self, code: _HaltCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def materialize_sql_snapshot(
    request: SqlSnapshotMaterializationRequest,
) -> SnapshotMaterializationResult:
    if type(request) is not SqlSnapshotMaterializationRequest:
        raise ValueError("request must be SqlSnapshotMaterializationRequest")
    stage = request.materialization_stage
    trust = _trust_for(stage)
    try:
        _checkpoint(request.context)
        mismatch = _ruleset_mismatch(request)
        if mismatch is not None:
            return _failed(stage, trust, (mismatch,))
        working = request
        if request.policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
            try:
                require_artifact_store(request.artifact_store)
            except ArtifactPublishError as exc:
                return _failed(stage, trust, (artifact_error_diagnostic(exc),))
            working = dataclasses.replace(request, policy=MaterializationPolicy.READERS_REQUIRED)
        if working.parse_result.status is ParseStatus.FAILED:
            return _failed(stage, trust, _parser_unavailable_diagnostics(working))
        selected = _select_tables(working)
        result = _materialize_selected(working, selected, stage, trust)
        if request.policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
            return _with_artifacts(result, request)
        return result
    except ArtifactPublishError as exc:
        return _failed(stage, trust, (artifact_error_diagnostic(exc),))
    except _Halt as halt:
        return _failed(
            stage,
            trust,
            (_error(halt.code, halt.message),),
        )


def _materialize_selected(
    request: SqlSnapshotMaterializationRequest,
    selected: tuple[ParsedTable, ...],
    stage: MaterializationStage,
    trust: CacheTrustLevel,
) -> SnapshotMaterializationResult:
    ruleset_index = compare_key_index(request.ruleset)
    descriptors: list[SnapshotTableDescriptor] = []
    published: list[SnapshotTable] = []
    diagnostics: list[MaterializationDiagnostic] = []
    for parsed in selected:
        _checkpoint(request.context)
        table_descriptor, table, table_diagnostics = _materialize_table(
            request, parsed, ruleset_index, stage
        )
        descriptors.append(table_descriptor)
        diagnostics.extend(table_diagnostics)
        if table is not None:
            published.append(table)
    ready = [item for item in descriptors if item.degraded_reason is not DegradedReason.TABLE_FAILED]
    failed_count = len(descriptors) - len(ready)
    if descriptors and not ready:
        if not diagnostics:
            diagnostics.append(
                _error(
                    MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                    "no table could be materialized",
                )
            )
        return _failed(stage, trust, tuple(diagnostics))
    status = (
        SnapshotMaterializationStatus.COMPLETE
        if failed_count == 0
        else SnapshotMaterializationStatus.PARTIAL
    )
    snapshot_id = secrets.token_hex(16)
    source_context = SnapshotSourceContext(
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        sql_source_digest=request.sql_source_digest,
    )
    tables = tuple(descriptors)
    snapshot_digest = snapshot_digest_of(
        stage=stage,
        parser_version=PARSER_VERSION,
        table_ruleset_version=request.table_ruleset_version,
        tables=tables,
    )
    raw_state = raw_state_digest_of(tables)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        source_kind=SourceKind.SQL_DUMP_SOURCE,
        parser_version=PARSER_VERSION,
        table_ruleset_version=request.table_ruleset_version,
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
        table_ruleset_version=request.table_ruleset_version,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        table_count=len(tables),
        tables=tables,
        source_context=source_context,
        diagnostics=tuple(diagnostics),
        row_count_total=sum(item.row_count for item in tables),
    )
    table_set: SnapshotTableSet | None = None
    if request.policy is MaterializationPolicy.READERS_REQUIRED:
        aligned: list[SnapshotTable] = []
        for item in published:
            aligned.append(
                SnapshotTable(
                    descriptor=item.descriptor,
                    reader=item.reader,
                    diagnostics=item.diagnostics,
                )
            )
        table_set = SnapshotTableSet(
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            table_ruleset_version=request.table_ruleset_version,
            tables=tuple(aligned),
            diagnostics=tuple(diagnostics),
        )
    return SnapshotMaterializationResult(
        status=status,
        materialization_stage=stage,
        cache_trust_level=trust,
        diagnostics=tuple(diagnostics),
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
    )


def _with_artifacts(
    result: SnapshotMaterializationResult,
    request: SqlSnapshotMaterializationRequest,
) -> SnapshotMaterializationResult:
    if (
        result.status is SnapshotMaterializationStatus.FAILED
        or result.snapshot is None
        or result.table_set is None
    ):
        return result
    store = require_artifact_store(request.artifact_store)
    published = publish_ready_tables(
        result.table_set.tables,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        context=request.context,
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


def _materialize_table(
    request: SqlSnapshotMaterializationRequest,
    parsed: ParsedTable,
    ruleset_index: dict[str, TableCompareKey],
    stage: MaterializationStage,
) -> tuple[
    SnapshotTableDescriptor,
    SnapshotTable | None,
    tuple[MaterializationDiagnostic, ...],
]:
    source = parsed.descriptor
    diagnostics: list[MaterializationDiagnostic] = []
    try:
        compare_keys = effective_key_columns(source, ruleset_index)
    except CompareKeyError as exc:
        diagnostic = _error(
            MaterializationDiagnosticCode.COMPARE_KEY_UNKNOWN_COLUMN,
            str(exc),
            table=source.canonical_name,
            column=exc.column,
        )
        descriptor = _failed_descriptor(source, stage, request.table_ruleset_version, ())
        return descriptor, None, (diagnostic,)
    schema_digest = compare_schema_digest(
        source.canonical_name,
        tuple(column.canonical_name for column in source.columns),
        compare_keys,
    )
    if parsed.reader is None:
        diagnostic = _error(
            MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
            "table has no READY reader",
            table=source.canonical_name,
        )
        descriptor = _failed_descriptor(
            source,
            stage,
            request.table_ruleset_version,
            compare_keys,
            schema_digest=schema_digest,
        )
        return descriptor, None, (diagnostic,)
    try:
        row_hashes, fast_hashes, duplicate = _consume_rows(
            parsed.reader, request.context, compare_keys
        )
    except _Halt as halt:
        parsed.reader.close()
        raise halt
    except (TableAccessError, CanonicalEncodingError, ValueError) as exc:
        parsed.reader.close()
        code = _map_stream_error(exc)
        diagnostic = _error(code, str(exc) or "table stream failed", table=source.canonical_name)
        descriptor = _failed_descriptor(
            source,
            stage,
            request.table_ruleset_version,
            compare_keys,
            schema_digest=schema_digest,
        )
        return descriptor, None, (diagnostic,)
    parsed.reader.close()
    degraded: DegradedReason | None = None
    if not compare_keys:
        degraded = DegradedReason.KEYLESS
    elif duplicate:
        degraded = DegradedReason.DUPLICATE_EFFECTIVE_KEY
        diagnostics.append(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode.DUPLICATE_EFFECTIVE_KEY,
                severity=DiagnosticSeverity.WARNING,
                message="duplicate effective key rows were preserved",
                table=source.canonical_name,
            )
        )
    fast_digest = fast_row_digest_of(fast_hashes)
    raw_digest = (
        raw_content_digest_of(row_hashes) if stage is MaterializationStage.FINAL else None
    )
    descriptor = SnapshotTableDescriptor(
        table_name=source.canonical_name,
        display_table_name=source.display_name,
        columns=tuple(
            SnapshotColumnDescriptor(
                name=column.canonical_name,
                display_name=column.display_name,
                nullable=column.nullable,
                scalar_type=column.sql_type,
            )
            for column in source.columns
        ),
        primary_key_columns=source.primary_key_canonical_names,
        compare_key_columns=compare_keys,
        row_count=len(row_hashes),
        materialization_stage=stage,
        compare_schema_digest=schema_digest,
        table_ruleset_version=request.table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        fast_row_digest=fast_digest,
        raw_content_digest=raw_digest,
        degraded_reason=degraded,
        diagnostics=tuple(diagnostics),
    )
    published: SnapshotTable | None = None
    if request.policy is MaterializationPolicy.READERS_REQUIRED:
        reopenable = as_reopenable(parsed.reader)
        if reopenable is None:
            diagnostic = _error(
                MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                "READY reader cannot reopen",
                table=source.canonical_name,
            )
            failed = _failed_descriptor(
                source,
                stage,
                request.table_ruleset_version,
                compare_keys,
                schema_digest=schema_digest,
            )
            return failed, None, (*diagnostics, diagnostic)
        published_source = as_reopenable(reopenable.reopen())
        if published_source is None:
            diagnostic = _error(
                MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                "READY reader cannot reopen",
                table=source.canonical_name,
            )
            failed = _failed_descriptor(
                source,
                stage,
                request.table_ruleset_version,
                compare_keys,
                schema_digest=schema_digest,
            )
            return failed, None, (*diagnostics, diagnostic)
        published = SnapshotTable(
            descriptor=descriptor,
            reader=BoundSnapshotTableReader(descriptor, published_source),
            diagnostics=tuple(diagnostics),
        )
    return descriptor, published, tuple(diagnostics)


def _consume_rows(
    reader: TableReader,
    context: ParserInvocationContext,
    compare_keys: tuple[str, ...],
) -> tuple[tuple[bytes, ...], tuple[bytes, ...], bool]:
    descriptor = reader.descriptor()
    columns = descriptor.columns
    key_indexes = _key_indexes(descriptor, compare_keys)
    row_hashes: list[bytes] = []
    fast_hashes: list[bytes] = []
    seen: set[tuple[bytes, ...]] = set()
    duplicate = False
    for row in reader.iter_rows():
        _checkpoint(context)
        row_hashes.append(row_content_hash(columns, row))
        fast_hashes.append(fast_row_hash(columns, row))
        if key_indexes:
            key = tuple(encode_cell_frame(columns[index], row[index]) for index in key_indexes)
            if key in seen:
                duplicate = True
            else:
                seen.add(key)
    _checkpoint(context)
    return tuple(row_hashes), tuple(fast_hashes), duplicate


def _key_indexes(
    descriptor: SourceTableDescriptor, compare_keys: tuple[str, ...]
) -> tuple[int, ...]:
    if not compare_keys:
        return ()
    names = {column.canonical_name: column.ordinal for column in descriptor.columns}
    return tuple(names[name] for name in compare_keys)


def _select_tables(request: SqlSnapshotMaterializationRequest) -> tuple[ParsedTable, ...]:
    tables = request.parse_result.tables
    if request.requested_tables is None:
        return tables
    by_name = {item.descriptor.canonical_name: item for item in tables}
    selected: list[ParsedTable] = []
    for name in request.requested_tables:
        canonical = canonicalize_identifier(name)
        table = by_name.get(canonical)
        if table is None:
            raise _Halt(
                MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
                f"requested table {canonical!r} is not in the parse result",
            )
        selected.append(table)
    return tuple(selected)


def _failed_descriptor(
    source: SourceTableDescriptor,
    stage: MaterializationStage,
    table_ruleset_version: int,
    compare_keys: tuple[str, ...],
    *,
    schema_digest: DigestRef | None = None,
) -> SnapshotTableDescriptor:
    columns = tuple(
        SnapshotColumnDescriptor(
            name=column.canonical_name,
            display_name=column.display_name,
            nullable=column.nullable,
            scalar_type=column.sql_type,
        )
        for column in source.columns
    )
    digest = schema_digest
    if digest is None:
        digest = compare_schema_digest(
            source.canonical_name,
            tuple(column.name for column in columns),
            compare_keys,
        )
    return SnapshotTableDescriptor(
        table_name=source.canonical_name,
        display_table_name=source.display_name,
        columns=columns,
        primary_key_columns=source.primary_key_canonical_names,
        compare_key_columns=compare_keys,
        row_count=0,
        materialization_stage=stage,
        compare_schema_digest=digest,
        table_ruleset_version=table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        degraded_reason=DegradedReason.TABLE_FAILED,
    )


def _ruleset_mismatch(
    request: SqlSnapshotMaterializationRequest,
) -> MaterializationDiagnostic | None:
    if (
        request.table_ruleset_version != request.ruleset.table_ruleset_version
        or request.table_ruleset_version != TABLE_RULESET_VERSION
    ):
        return _error(
            MaterializationDiagnosticCode.RULESET_VERSION_MISMATCH,
            "table_ruleset_version does not match the injected snapshot",
        )
    return None


def _parser_unavailable_diagnostics(
    request: SqlSnapshotMaterializationRequest,
) -> tuple[MaterializationDiagnostic, ...]:
    copied: list[MaterializationDiagnostic] = []
    for item in request.parse_result.diagnostics:
        copied.append(
            _error(
                MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                item.message,
                table=item.table,
                column=item.column,
            )
        )
    if not copied:
        copied.append(
            _error(
                MaterializationDiagnosticCode.TABLE_READER_UNAVAILABLE,
                "SQL parse result is FAILED",
            )
        )
    return tuple(copied)


def _checkpoint(context: ParserInvocationContext) -> None:
    if context.cancel_requested.is_set():
        raise _Halt(MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED, "materialization cancelled")
    deadline = context.deadline_monotonic
    if deadline is not None and time.monotonic() >= deadline:
        raise _Halt(
            MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT,
            "materialization deadline exceeded",
        )


def _map_stream_error(exc: BaseException) -> MaterializationDiagnosticCode:
    if isinstance(exc, TableAccessError):
        if exc.code is ParserDiagnosticCode.PARSER_CANCELLED:
            return MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED
        if exc.code is ParserDiagnosticCode.PARSER_TIMEOUT:
            return MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT
    return MaterializationDiagnosticCode.STREAM_INCOMPLETE


def _trust_for(stage: MaterializationStage) -> CacheTrustLevel:
    if stage is MaterializationStage.PROVISIONAL:
        return CacheTrustLevel.PROVISIONAL
    return CacheTrustLevel.CONTENT_VERIFIED


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
    column: str | None = None,
) -> MaterializationDiagnostic:
    return MaterializationDiagnostic(
        code=code,
        severity=DiagnosticSeverity.ERROR,
        message=message,
        table=table,
        column=column,
    )
