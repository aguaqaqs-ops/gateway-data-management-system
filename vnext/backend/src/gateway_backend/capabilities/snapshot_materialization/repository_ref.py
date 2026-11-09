"""RepositoryRef Snapshot materializer. Consumes the provider protocol only."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import time
from datetime import UTC, datetime

from gateway_shared_kernel import canonicalize_identifier

from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    raw_state_digest_of,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    artifact_error_diagnostic,
    publish_canonical_tables,
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
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    CanonicalTableIdentity,
    CanonicalBinding,
    CommittedCanonicalTablesPort,
    RepositoryRef,
    RepositoryRefTimeoutPolicy,
    SourceKind,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    map_repository_column,
)
from gateway_backend.capabilities.table_access import kernel_control_scope
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_VERSION,
    ParserInvocationContext,
    SourceTableDescriptor,
)
from gateway_backend.capabilities.table_rules.contracts import (
    StorageRuleView,
    TABLE_RULESET_VERSION,
)
from gateway_backend.capabilities.snapshot_materialization._ruleset import (
    CompareKeyError,
    compare_key_index,
    effective_key_columns,
)

_HaltCode = MaterializationDiagnosticCode
_LOGGER = logging.getLogger(__name__)


class _Halt(Exception):
    def __init__(
        self,
        code: _HaltCode,
        message: str,
        *,
        table: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.table = table


def materialize_repository_ref(
    request: RepositoryRefMaterializationRequest,
) -> SnapshotMaterializationResult:
    return _run_materializer(request, complete_table_set=False)


def _run_materializer(
    request: RepositoryRefMaterializationRequest, *, complete_table_set: bool,
) -> SnapshotMaterializationResult:
    if type(request) is not RepositoryRefMaterializationRequest:
        raise ValueError("request must be RepositoryRefMaterializationRequest")
    stage = request.materialization_stage
    trust = CacheTrustLevel.CONTENT_VERIFIED
    try:
        with kernel_control_scope(request.context.cancel_requested, request.context.deadline_monotonic):
            return _materialize(request, stage, trust, complete_table_set=complete_table_set)
    except ArtifactPublishError as exc:
        return _failed(stage, trust, (_error(exc.code, exc.message, table=exc.table),))
    except _Halt as halt:
        return _failed(
            stage,
            trust,
            (
                _error(
                    halt.code,
                    halt.message,
                    table=halt.table,
                ),
            ),
        )


def describe_repository_ref(
    request: RepositoryRefMaterializationRequest,
) -> SnapshotMaterializationResult:
    """Verify a complete exact-commit description before any row demand is known."""
    ref = request.repository_ref.ref
    if not ref or ref in ("main", "HEAD") or ref.startswith("refs/"):
        return _failed(request.materialization_stage, CacheTrustLevel.CONTENT_VERIFIED,
            (_error(MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
                    "canonical description requires an exact immutable commit"),))
    result = _run_materializer(dataclasses.replace(request,
        policy=MaterializationPolicy.READERS_REQUIRED, requested_tables=(), export_tables=()),
        complete_table_set=True)
    if (result.snapshot is not None
            and result.snapshot.source_context.resolved_commit_hash != ref):
        return _failed(request.materialization_stage, CacheTrustLevel.CONTENT_VERIFIED,
            (_error(MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
                    "canonical description is not pinned to the requested exact commit"),))
    return result


def ensure_committed_tables(
    table_set: SnapshotTableSet, *, repository_ref: RepositoryRef,
    canonical_binding: CanonicalBinding, committed_tables: CommittedCanonicalTablesPort,
    requested_tables: tuple[str, ...], context: ParserInvocationContext,
    timeout_policy: RepositoryRefTimeoutPolicy | None = None,
) -> SnapshotTableSet:
    """Fill only missing readers for this exact metadata/commit, retaining the full set."""
    with kernel_control_scope(context.cancel_requested, context.deadline_monotonic) as active:
        upper = 64 * 1024 + len(table_set.tables) * 1024
        upper += sum(len(table.descriptor.table_name) * 64 for table in table_set.tables)
        upper += sum(len(name) * 64 + 1024 for name in requested_tables)
        with active.memory.reserve(upper):
            result = _ensure_committed_tables(table_set, repository_ref=repository_ref,
                canonical_binding=canonical_binding, committed_tables=committed_tables,
                requested_tables=requested_tables, context=context, timeout_policy=timeout_policy)
            active.memory.retain_metadata(result, 4096 + len(result.tables) * 512)
            return result


def _ensure_committed_tables(
    table_set: SnapshotTableSet, *, repository_ref: RepositoryRef,
    canonical_binding: CanonicalBinding, committed_tables: CommittedCanonicalTablesPort,
    requested_tables: tuple[str, ...], context: ParserInvocationContext,
    timeout_policy: RepositoryRefTimeoutPolicy | None,
) -> SnapshotTableSet:
    _checkpoint(context)
    commit_id = repository_ref.ref
    if not commit_id or commit_id in ("main", "HEAD") or commit_id.startswith("refs/"):
        raise ValueError("row materialization requires an exact immutable commit")
    if committed_tables.repository_id != repository_ref.repository_id:
        raise ValueError("committed table owner differs from the requested repository scope")
    names = tuple(canonicalize_identifier(name) for name in requested_tables)
    if len(set(names)) != len(names):
        raise ValueError("row demands must be unique canonical table names")
    tables = {table.descriptor.table_name: table for table in table_set.tables}
    views = {view.canonical_table: view for view in canonical_binding.tables}
    identities = {identity.canonical_table: identity for identity in canonical_binding.table_identities}
    if (set(tables) != set(views) or set(identities) != set(views)
            or any(name not in tables for name in names)):
        raise ValueError("row demands and complete canonical binding disagree")
    loaded: list[SnapshotTable] = []
    try:
        for name in names:
            _checkpoint(context)
            current = tables[name]
            if current.reader is not None:
                continue
            table = committed_tables.load_table(commit_id=commit_id, descriptor=current.descriptor,
                identity=identities[name], storage_view=views[name], context=context,
                timeout_policy=timeout_policy)
            loaded.append(table)
            tables[name] = table
        _checkpoint(context)
        return dataclasses.replace(table_set,
            tables=tuple(tables[table.descriptor.table_name] for table in table_set.tables))
    except BaseException:
        for table in loaded:
            if table.reader is not None:
                table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
        raise


def _materialize(
    request: RepositoryRefMaterializationRequest,
    stage: MaterializationStage,
    trust: CacheTrustLevel,
    *, complete_table_set: bool,
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
        result = _materialize_open_session(working, session, stage, trust,
            complete_table_set=complete_table_set)
        if original_policy is MaterializationPolicy.ARTIFACTS_REQUIRED:
            result = _with_artifacts(result, request)
    except ArtifactPublishError as exc:
        result = _failed(stage, trust, (artifact_error_diagnostic(exc),))
    except _Halt as halt:
        result = _failed(
            stage,
            trust,
            (
                _error(
                    halt.code,
                    halt.message,
                    table=halt.table,
                ),
            ),
        )
    except RepositoryProviderError as exc:
        if exc.retryable:
            raise
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
    *, complete_table_set: bool,
) -> SnapshotMaterializationResult:
    _checkpoint(request.context)
    pinned = session.pinned_commit_hash()
    if type(pinned) is not str or pinned == "":
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
            "open_ref must pin a resolved commit hash",
        )
    catalog = session.get_catalog()
    if catalog.repository_id != request.repository_ref.repository_id:
        raise _Halt(MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
                    "catalog repository differs from the requested repository scope")
    if catalog.resolved_commit_hash != pinned:
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
            "catalog commit is not pinned to the session commit",
        )
    indexed = _index_catalog(catalog)
    binding = request.canonical_binding
    if binding.is_initial and catalog.tables:
        raise _Halt(
            MaterializationDiagnosticCode.INITIAL_BASELINE_NOT_EMPTY,
            "INITIAL baseline Repository commit contains user tables",
        )
    binding_by_name = {item.canonical_table: item for item in binding.tables}
    if set(binding_by_name) != set(indexed):
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
            "Repository catalog table set does not match canonical metadata",
        )
    selected_names = _selected_names(request, binding_by_name)
    selected_set = set(selected_names)
    export_set = _export_names(request, binding_by_name)
    materialized_set = selected_set | export_set
    identities = {item.canonical_table: item for item in binding.table_identities}
    if set(identities) != set(binding_by_name):
        raise _Halt(MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                    "canonical metadata must cover every table before row materialization")
    diagnostics: list[MaterializationDiagnostic] = []
    published: list[SnapshotTable] = []
    descriptors: list[SnapshotTableDescriptor] = []
    for name in sorted(binding_by_name, key=lambda item: item.encode("utf-8")):
        _checkpoint(request.context)
        catalog_table = indexed[name]
        storage_view = binding_by_name[name]
        if request.committed_tables is None:
            raise ValueError("repository tables require scoped committed canonical access")
        if request.committed_tables.repository_id != request.repository_ref.repository_id:
            raise _Halt(MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                        "canonical table owner differs from the requested repository scope")
        identity = identities[name]
        descriptor = _describe_without_rows(request, catalog_table, identity, stage, storage_view)
        table = request.committed_tables.describe_table(commit_id=pinned, descriptor=descriptor,
            identity=identity, storage_view=storage_view, context=request.context,
            timeout_policy=request.timeout_policy)
        descriptors.append(descriptor)
        diagnostics.extend(table.diagnostics)
        published.append(table)
    # Complete catalog/manifest binding is established for every table before
    # opening any rows. A later bad table cannot hide behind an earlier cache hit.
    try:
        for index, table in enumerate(published):
            name = table.descriptor.table_name
            if name not in materialized_set:
                continue
            assert request.committed_tables is not None
            published[index] = request.committed_tables.load_table(commit_id=pinned,
                descriptor=table.descriptor, identity=identities[name], storage_view=binding_by_name[name],
                context=request.context, timeout_policy=request.timeout_policy)
    except BaseException:
        for table in published:
            if table.reader is not None:
                table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
        raise
    selected = tuple(descriptors)
    parser_version = request.parser_version or PARSER_VERSION
    source_context = SnapshotSourceContext(
        source_kind=SourceKind.IMMUTABLE_REPOSITORY_REF,
        repository_id=request.repository_ref.repository_id,
        repository_ref=request.repository_ref.ref,
        resolved_commit_hash=pinned,
    )
    snapshot_id = hashlib.sha256(
        f"{request.repository_ref.repository_id}:{pinned}".encode("utf-8")
    ).hexdigest()[:32]
    computed_snapshot_digest = snapshot_digest_of(
        stage=stage,
        parser_version=parser_version,
        table_ruleset_version=request.table_ruleset_version,
        tables=selected,
    )
    snapshot_digest = computed_snapshot_digest
    raw_state = raw_state_digest_of(selected)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        source_kind=SourceKind.IMMUTABLE_REPOSITORY_REF,
        parser_version=parser_version,
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
        parser_version=parser_version,
        table_ruleset_version=request.table_ruleset_version,
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
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            table_ruleset_version=request.table_ruleset_version,
            tables=tuple(table for table in published
                if complete_table_set or table.descriptor.table_name in materialized_set),
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


def _describe_without_rows(
    request: RepositoryRefMaterializationRequest,
    catalog_table: RepositoryCatalogTable,
    identity: CanonicalTableIdentity,
    stage: MaterializationStage,
    storage_view: StorageRuleView,
) -> SnapshotTableDescriptor:
    table_name = canonicalize_identifier(catalog_table.table_name)
    mapped_columns = tuple(map_repository_column(column) for column in catalog_table.columns)
    source_columns = tuple(item.source for item in mapped_columns)
    source_descriptor = SourceTableDescriptor(
        display_name=catalog_table.display_table_name or catalog_table.table_name,
        canonical_name=table_name,
        columns=source_columns,
        primary_key_canonical_names=tuple(
            canonicalize_identifier(name) for name in catalog_table.primary_key_columns
        ),
        reader_ready=True,
    )
    if request.frozen_storage_only:
        compare_keys = storage_view.canonical_key_columns
    else:
        assert request.ruleset is not None
        try:
            compare_keys = effective_key_columns(source_descriptor, compare_key_index(request.ruleset))
        except CompareKeyError as exc:
            raise _Halt(
                MaterializationDiagnosticCode.COMPARE_KEY_UNKNOWN_COLUMN,
                str(exc),
                table=table_name,
            ) from exc
    if catalog_table.row_count is not None and catalog_table.row_count != identity.row_count:
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_ROW_COUNT_MISMATCH,
            "Repository catalog row count differs from canonical metadata",
            table=table_name,
        )
    columns = tuple(
        SnapshotColumnDescriptor(
            name=column.canonical_name,
            display_name=column.display_name,
            nullable=column.nullable,
            scalar_type=column.sql_type,
        )
        for column in source_columns
    )
    return SnapshotTableDescriptor(
        table_name=table_name,
        display_table_name=source_descriptor.display_name,
        columns=columns,
        primary_key_columns=source_descriptor.primary_key_canonical_names,
        compare_key_columns=compare_keys,
        row_count=identity.row_count,
        materialization_stage=stage,
        compare_schema_digest=compare_schema_digest(
            table_name,
            tuple(column.canonical_name for column in source_columns),
            compare_keys,
        ),
        table_ruleset_version=request.table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=identity.raw_content_digest,
        degraded_reason=None if compare_keys else DegradedReason.KEYLESS,
    )


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


def _selected_names(
    request: RepositoryRefMaterializationRequest,
    binding_by_name: dict[str, StorageRuleView],
) -> tuple[str, ...]:
    if request.requested_tables is None:
        return tuple(sorted(binding_by_name, key=lambda item: item.encode("utf-8")))
    selected = tuple(canonicalize_identifier(name) for name in request.requested_tables)
    if len(set(selected)) != len(selected):
        raise _Halt(
            MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
            "requested tables must not contain duplicates",
        )
    missing = tuple(name for name in selected if name not in binding_by_name)
    if missing:
        raise _Halt(
            MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
            f"requested table {missing[0]!r} is not in canonical metadata",
        )
    return selected


def _export_names(
    request: RepositoryRefMaterializationRequest,
    binding_by_name: dict[str, StorageRuleView],
) -> set[str]:
    if request.export_tables is None:
        return set()
    selected = tuple(canonicalize_identifier(name) for name in request.export_tables)
    if len(set(selected)) != len(selected):
        raise _Halt(
            MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
            "export tables must not contain duplicates",
        )
    missing = tuple(name for name in selected if name not in binding_by_name)
    if missing:
        raise _Halt(
            MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING,
            f"export table {missing[0]!r} is not in canonical metadata",
        )
    return set(selected)


def _ruleset_mismatch(
    request: RepositoryRefMaterializationRequest,
) -> MaterializationDiagnostic | None:
    if request.frozen_storage_only:
        if request.table_ruleset_version == TABLE_RULESET_VERSION:
            return None
        return _error(
            MaterializationDiagnosticCode.RULESET_VERSION_MISMATCH,
            "table_ruleset_version does not match the frozen storage reader",
        )
    assert request.ruleset is not None
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
    published = publish_canonical_tables(
        result.table_set.tables,
        snapshot_digest=result.snapshot.snapshot_digest,
        store=store,
        repository_id=request.repository_ref.repository_id,
        lookup=None if request.committed_tables is None else request.committed_tables.lookup,
        before_write=None if request.committed_tables is None else request.committed_tables.register,
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
