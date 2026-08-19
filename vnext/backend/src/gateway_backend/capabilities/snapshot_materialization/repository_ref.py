"""RepositoryRef Snapshot materializer. Consumes the provider protocol only."""

from __future__ import annotations

import dataclasses
import time
from datetime import UTC, datetime

from gateway_shared_kernel import CanonicalEncodingError, canonicalize_identifier

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
    CacheTrustLevel,
    DiagnosticSeverity,
    HiddenFinalSummary,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryCatalogTable,
    RepositoryProviderError,
    RepositoryRefMaterializationRequest,
    RepositoryRefSession,
    RepositoryTableCatalog,
    Snapshot,
    SnapshotMaterializationResult,
    SnapshotMaterializationStatus,
    SnapshotSourceContext,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    SourceKind,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_backend.capabilities.table_access.contracts import (
    MaterializedTableReader,
    ParserInvocationContext,
    SourceRow,
    SourceTableDescriptor,
)
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION

_HaltCode = MaterializationDiagnosticCode


class _Halt(Exception):
    def __init__(self, code: _HaltCode, message: str, *, table: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.table = table


def materialize_repository_ref(
    request: RepositoryRefMaterializationRequest,
) -> SnapshotMaterializationResult:
    if type(request) is not RepositoryRefMaterializationRequest:
        raise ValueError("request must be RepositoryRefMaterializationRequest")
    stage = request.materialization_stage
    trust = CacheTrustLevel.CONTENT_VERIFIED
    try:
        return _materialize(request, stage, trust)
    except ArtifactPublishError as exc:
        return _failed(stage, trust, (_error(exc.code, exc.message, table=exc.table),))
    except _Halt as halt:
        return _failed(stage, trust, (_error(halt.code, halt.message, table=halt.table),))


def _materialize(
    request: RepositoryRefMaterializationRequest,
    stage: MaterializationStage,
    trust: CacheTrustLevel,
) -> SnapshotMaterializationResult:
    _checkpoint(request.context)
    mismatch = _ruleset_mismatch(request)
    if mismatch is not None:
        return _failed(stage, trust, (mismatch,))
    original_policy = request.policy
    working = request
    if request.policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
        require_artifact_store(request.artifact_store)
        working = _with_readers_policy(request)
    session: RepositoryRefSession | None = None
    close_diagnostic: MaterializationDiagnostic | None = None
    try:
        session = working.provider.open_ref(working.repository_ref, working.timeout_policy)
        result = _materialize_open_session(working, session, stage, trust)
        if original_policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
            result = _with_artifacts(result, request)
    except ArtifactPublishError as exc:
        result = _failed(stage, trust, (artifact_error_diagnostic(exc),))
    except _Halt as halt:
        result = _failed(stage, trust, (_error(halt.code, halt.message, table=halt.table),))
    except RepositoryProviderError as exc:
        result = _failed(stage, trust, (_error(exc.code, exc.message, table=exc.table),))
    finally:
        if session is not None:
            try:
                session.close()
            except RepositoryProviderError as exc:
                close_diagnostic = _close_diagnostic(exc)
            except Exception as exc:
                close_diagnostic = MaterializationDiagnostic(
                    code=MaterializationDiagnosticCode.REPOSITORY_SESSION_CLOSE_FAILED,
                    severity=DiagnosticSeverity.WARNING,
                    message=str(exc) or "repository session close failed",
                )
    if close_diagnostic is not None:
        return _with_diagnostic(result, close_diagnostic)
    return result


def _materialize_open_session(
    request: RepositoryRefMaterializationRequest,
    session: RepositoryRefSession,
    stage: MaterializationStage,
    trust: CacheTrustLevel,
) -> SnapshotMaterializationResult:
    _checkpoint(request.context)
    pinned = session.pinned_commit_hash()
    if type(pinned) is not str or pinned == "":
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
            "open_ref must pin a resolved commit hash",
        )
    hidden = session.read_hidden_summary()
    if hidden is None:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_MISSING,
            "hidden FINAL summary is missing",
        )
    version_error = _hidden_version_mismatch(request, hidden)
    if version_error is not None:
        return _failed(stage, trust, (version_error,))
    if hidden.materialization_stage is not MaterializationStage.FINAL:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT,
            "hidden summary is not FINAL",
        )
    recomputed = snapshot_digest_of(
        stage=hidden.materialization_stage,
        parser_version=hidden.parser_version,
        table_ruleset_version=hidden.table_ruleset_version,
        tables=hidden.tables,
    )
    if recomputed != hidden.snapshot_digest:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT,
            "hidden snapshot_digest does not match stored descriptors",
        )
    if raw_state_digest_of(hidden.tables) != hidden.raw_state_digest:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT,
            "hidden raw_state_digest does not match stored descriptors",
        )
    _checkpoint(request.context)
    catalog = session.get_catalog()
    if catalog.resolved_commit_hash != pinned:
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
            "catalog commit is not pinned to the session commit",
        )
    indexed = _index_catalog(catalog)
    selected = _select_hidden_tables(hidden, indexed, request.requested_tables)
    diagnostics: list[MaterializationDiagnostic] = []
    for table in selected:
        catalog_table = indexed[table.table_name]
        mapped_columns = tuple(map_repository_column(column) for column in catalog_table.columns)
        column_names = tuple(item.source.canonical_name for item in mapped_columns)
        schema = compare_schema_digest(table.table_name, column_names, table.compare_key_columns)
        if schema != table.compare_schema_digest:
            raise _Halt(
                MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
                "catalog compare schema does not match hidden summary",
                table=table.table_name,
            )
        hidden_names = tuple(column.name for column in table.columns)
        if column_names != hidden_names:
            raise _Halt(
                MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
                "catalog columns do not match hidden summary",
                table=table.table_name,
            )
    published: list[SnapshotTable] = []
    if request.policy is MaterializationPolicy.READERS_REQUIRED:
        for table in selected:
            _checkpoint(request.context)
            catalog_table = indexed[table.table_name]
            source_reader, table_diagnostics = _read_and_validate_table(
                request, session, catalog_table, table
            )
            diagnostics.extend(table_diagnostics)
            published.append(
                SnapshotTable(
                    descriptor=table,
                    reader=BoundSnapshotTableReader(table, source_reader),
                    diagnostics=tuple(table_diagnostics),
                )
            )
    source_context = SnapshotSourceContext(
        source_kind=SourceKind.IMMUTABLE_REPOSITORY_REF,
        repository_id=request.repository_ref.repository_id,
        repository_ref=request.repository_ref.ref,
        resolved_commit_hash=pinned,
    )
    snapshot_digest = snapshot_digest_of(
        stage=stage,
        parser_version=hidden.parser_version,
        table_ruleset_version=hidden.table_ruleset_version,
        tables=selected,
    )
    raw_state = raw_state_digest_of(selected)
    snapshot = Snapshot(
        snapshot_id=hidden.snapshot_id,
        source_kind=SourceKind.IMMUTABLE_REPOSITORY_REF,
        parser_version=hidden.parser_version,
        table_ruleset_version=hidden.table_ruleset_version,
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
        snapshot_id=hidden.snapshot_id,
        snapshot_digest=snapshot_digest,
        raw_state_digest=raw_state,
        materialization_stage=stage,
        parser_version=hidden.parser_version,
        table_ruleset_version=hidden.table_ruleset_version,
        summary_contract_version=SUMMARY_CONTRACT_VERSION,
        table_count=len(selected),
        tables=selected,
        source_context=source_context,
        diagnostics=tuple(diagnostics),
        row_count_total=sum(item.row_count for item in selected),
    )
    table_set: SnapshotTableSet | None = None
    if request.policy is MaterializationPolicy.READERS_REQUIRED:
        table_set = SnapshotTableSet(
            snapshot_id=hidden.snapshot_id,
            snapshot_digest=snapshot_digest,
            table_ruleset_version=hidden.table_ruleset_version,
            tables=tuple(published),
            diagnostics=tuple(diagnostics),
        )
    return SnapshotMaterializationResult(
        status=SnapshotMaterializationStatus.COMPLETE,
        materialization_stage=stage,
        cache_trust_level=trust,
        diagnostics=tuple(diagnostics),
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
    )


def _read_and_validate_table(
    request: RepositoryRefMaterializationRequest,
    session: RepositoryRefSession,
    catalog_table: RepositoryCatalogTable,
    hidden_table: SnapshotTableDescriptor,
) -> tuple[MaterializedTableReader, tuple[MaterializationDiagnostic, ...]]:
    try:
        reader = session.open_table_reader(catalog_table.table_name)
    except RepositoryProviderError as exc:
        raise _Halt(exc.code, exc.message, table=hidden_table.table_name) from exc
    diagnostics: list[MaterializationDiagnostic] = []
    encoded_rows: list[SourceRow] = []
    try:
        for raw in reader.stream_rows():
            _checkpoint(request.context)
            try:
                encoded = encode_repository_row(
                    catalog_table.columns, raw, table=hidden_table.table_name
                )
            except ValueError as exc:
                raise _Halt(
                    MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
                    str(exc) or "repository row is malformed",
                    table=hidden_table.table_name,
                ) from exc
            diagnostics.extend(encoded.diagnostics)
            encoded_rows.append(encoded.cells)
    except RepositoryProviderError as exc:
        raise _Halt(exc.code, exc.message, table=hidden_table.table_name) from exc
    finally:
        reader.close()
    mapped = tuple(map_repository_column(column) for column in catalog_table.columns)
    source_columns = tuple(item.source for item in mapped)
    try:
        row_hashes = tuple(row_content_hash(source_columns, row) for row in encoded_rows)
        fast_hashes = tuple(fast_row_hash(source_columns, row) for row in encoded_rows)
    except (CanonicalEncodingError, ValueError) as exc:
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
            str(exc) or "repository scalar encoding failed",
            table=hidden_table.table_name,
        ) from exc
    raw_digest = raw_content_digest_of(row_hashes)
    fast_digest = fast_row_digest_of(fast_hashes)
    if len(encoded_rows) != hidden_table.row_count:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
            "row count does not match hidden summary",
            table=hidden_table.table_name,
        )
    if hidden_table.raw_content_digest is None or raw_digest != hidden_table.raw_content_digest:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
            "raw_content_digest does not match hidden summary",
            table=hidden_table.table_name,
        )
    if hidden_table.fast_row_digest is not None and fast_digest != hidden_table.fast_row_digest:
        raise _Halt(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
            "fast_row_digest does not match hidden summary",
            table=hidden_table.table_name,
        )
    source_descriptor = SourceTableDescriptor(
        display_name=catalog_table.display_table_name or catalog_table.table_name,
        canonical_name=hidden_table.table_name,
        columns=source_columns,
        primary_key_canonical_names=tuple(
            canonicalize_identifier(name) for name in catalog_table.primary_key_columns
        ),
        reader_ready=True,
    )
    return MaterializedTableReader(source_descriptor, tuple(encoded_rows)), tuple(diagnostics)


def _index_catalog(catalog: RepositoryTableCatalog) -> dict[str, RepositoryCatalogTable]:
    indexed: dict[str, RepositoryCatalogTable] = {}
    seen_canonical: set[str] = set()
    for table in catalog.tables:
        canonical = canonicalize_identifier(table.table_name)
        if canonical in seen_canonical:
            raise _Halt(
                MaterializationDiagnosticCode.REPOSITORY_IDENTIFIER_COLLISION,
                f"catalog table name {table.table_name!r} collides after canonicalization",
                table=canonical,
            )
        seen_canonical.add(canonical)
        column_seen: set[str] = set()
        for column in table.columns:
            mapped = map_repository_column(column)
            if mapped.source.canonical_name in column_seen:
                raise _Halt(
                    MaterializationDiagnosticCode.REPOSITORY_IDENTIFIER_COLLISION,
                    f"catalog column {column.name!r} collides after canonicalization",
                    table=canonical,
                )
            column_seen.add(mapped.source.canonical_name)
        indexed[canonical] = table
    return indexed


def _select_hidden_tables(
    hidden: HiddenFinalSummary,
    indexed: dict[str, RepositoryCatalogTable],
    requested: tuple[str, ...] | None,
) -> tuple[SnapshotTableDescriptor, ...]:
    by_name = {table.table_name: table for table in hidden.tables}
    if requested is None:
        selected_names = tuple(table.table_name for table in hidden.tables)
    else:
        selected_names = tuple(canonicalize_identifier(name) for name in requested)
    selected: list[SnapshotTableDescriptor] = []
    for name in selected_names:
        hidden_table = by_name.get(name)
        if hidden_table is None:
            if name not in indexed:
                raise _Halt(
                    MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
                    f"requested table {name!r} is not in the catalog",
                )
            raise _Halt(
                MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
                f"table {name!r} is not in the hidden summary",
                table=name,
            )
        if name not in indexed:
            raise _Halt(
                MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
                f"hidden summary table {name!r} is missing from the catalog",
                table=name,
            )
        selected.append(hidden_table)
    return tuple(selected)


def _hidden_version_mismatch(
    request: RepositoryRefMaterializationRequest,
    hidden: HiddenFinalSummary,
) -> MaterializationDiagnostic | None:
    if hidden.table_ruleset_version != request.table_ruleset_version:
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary table_ruleset_version does not match the request",
        )
    if hidden.scalar_encoding_version != request.scalar_encoding_version:
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary scalar_encoding_version does not match the request",
        )
    if (
        hidden.snapshot_materialization_contract_version
        != request.snapshot_materialization_contract_version
    ):
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary snapshot_materialization_contract_version does not match",
        )
    if hidden.digest_contract_version != request.digest_contract_version:
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary digest_contract_version does not match the request",
        )
    if hidden.summary_contract_version != SUMMARY_CONTRACT_VERSION:
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary summary_contract_version is unsupported",
        )
    if request.parser_version is not None and hidden.parser_version != request.parser_version:
        return _error(
            MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH,
            "hidden summary parser_version does not match the request",
        )
    return None


def _ruleset_mismatch(
    request: RepositoryRefMaterializationRequest,
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


def _with_readers_policy(
    request: RepositoryRefMaterializationRequest,
) -> RepositoryRefMaterializationRequest:
    if request.policy is MaterializationPolicy.READERS_REQUIRED:
        return request
    return dataclasses.replace(request, policy=MaterializationPolicy.READERS_REQUIRED)


def _with_artifacts(
    result: SnapshotMaterializationResult,
    request: RepositoryRefMaterializationRequest,
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


def _checkpoint(context: ParserInvocationContext) -> None:
    if context.cancel_requested.is_set():
        raise _Halt(MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED, "materialization cancelled")
    deadline = context.deadline_monotonic
    if deadline is not None and time.monotonic() >= deadline:
        raise _Halt(
            MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT,
            "materialization deadline exceeded",
        )


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


def _close_diagnostic(exc: RepositoryProviderError) -> MaterializationDiagnostic:
    return MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.REPOSITORY_SESSION_CLOSE_FAILED,
        severity=DiagnosticSeverity.WARNING,
        message=exc.message,
        table=exc.table,
    )


def _with_diagnostic(
    result: SnapshotMaterializationResult,
    diagnostic: MaterializationDiagnostic,
) -> SnapshotMaterializationResult:
    combined = (*result.diagnostics, diagnostic)
    if result.status is SnapshotMaterializationStatus.FAILED:
        return _failed(result.materialization_stage, result.cache_trust_level, combined)
    assert result.snapshot is not None
    assert result.summary is not None
    summary = SnapshotSummary(
        snapshot_id=result.summary.snapshot_id,
        snapshot_digest=result.summary.snapshot_digest,
        raw_state_digest=result.summary.raw_state_digest,
        materialization_stage=result.summary.materialization_stage,
        parser_version=result.summary.parser_version,
        table_ruleset_version=result.summary.table_ruleset_version,
        summary_contract_version=result.summary.summary_contract_version,
        table_count=result.summary.table_count,
        tables=result.summary.tables,
        source_context=result.summary.source_context,
        diagnostics=combined,
        row_count_total=result.summary.row_count_total,
        business_state_digest=result.summary.business_state_digest,
    )
    table_set = result.table_set
    if table_set is not None:
        table_set = SnapshotTableSet(
            snapshot_id=table_set.snapshot_id,
            snapshot_digest=table_set.snapshot_digest,
            table_ruleset_version=table_set.table_ruleset_version,
            tables=table_set.tables,
            diagnostics=combined,
        )
    return SnapshotMaterializationResult(
        status=result.status,
        materialization_stage=result.materialization_stage,
        cache_trust_level=result.cache_trust_level,
        diagnostics=combined,
        snapshot=result.snapshot,
        summary=summary,
        table_set=table_set,
    )
