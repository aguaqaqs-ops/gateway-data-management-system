"""RepositoryRef Snapshot materializer. Consumes the provider protocol only."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import time
from datetime import UTC, datetime

from gateway_shared_kernel import CanonicalEncodingError, canonicalize_identifier

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableArtifactCacheKey
from gateway_backend.capabilities.snapshot_materialization._digest import (
    compare_schema_digest,
    encode_cell_frame,
    raw_content_digest_of,
    raw_state_digest_of,
    row_content_hash,
    snapshot_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    artifact_error_diagnostic,
    open_cached_snapshot_table,
    publish_ready_tables,
    require_artifact_store,
    row_layout_digest_of,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
    CacheTrustLevel,
    BlankRowProvenance,
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
    SnapshotTableOrderedMetadata,
    SnapshotTableDescriptor,
    SnapshotTableSet,
    CanonicalTableIdentity,
    SourceKind,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_backend.capabilities.table_access.contracts import (
    MaterializedTableReader,
    PARSER_VERSION,
    ParserInvocationContext,
    SourceColumnDescriptor,
    SourceRow,
    SourceTableDescriptor,
)
from gateway_backend.capabilities.table_rules.contracts import (
    OrderedPolicy,
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
    if type(request) is not RepositoryRefMaterializationRequest:
        raise ValueError("request must be RepositoryRefMaterializationRequest")
    stage = request.materialization_stage
    trust = CacheTrustLevel.CONTENT_VERIFIED
    try:
        return _materialize(request, stage, trust)
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
) -> SnapshotMaterializationResult:
    _checkpoint(request.context)
    pinned = session.pinned_commit_hash()
    if type(pinned) is not str or pinned == "":
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_REF_OPEN_FAILED,
            "open_ref must pin a resolved commit hash",
        )
    catalog = session.get_catalog()
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
    identities = {item.canonical_table: item for item in binding.table_identities}
    if request.requested_tables is not None and set(binding_by_name) - selected_set:
        if set(identities) != set(binding_by_name):
            raise _Halt(
                MaterializationDiagnosticCode.REPOSITORY_CATALOG_LOAD_FAILED,
                "canonical metadata is required for tables excluded from row materialization",
            )
    cache_candidates: dict[
        str,
        tuple[
            SnapshotTableDescriptor,
            tuple[SourceColumnDescriptor, ...],
            SnapshotTableOrderedMetadata | None,
            SnapshotTableArtifactCacheKey,
        ],
    ] = {}
    cached_row_refs: dict[SnapshotTableArtifactCacheKey, ArtifactRef] = {}
    cache_store: ArtifactStorePort | None = None
    if (
        request.policy is MaterializationPolicy.READERS_REQUIRED
        and request.export_cache is not None
        and request.artifact_store is not None
    ):
        cache_store = require_artifact_store(request.artifact_store)
        for name in sorted(selected_set, key=lambda item: item.encode("utf-8")):
            identity = identities.get(name)
            if identity is None:
                continue
            catalog_table = indexed[name]
            storage_view = binding_by_name[name]
            descriptor = _describe_without_rows(request, catalog_table, identity, stage)
            source_columns = tuple(
                map_repository_column(column).source for column in catalog_table.columns
            )
            ordered_metadata = _ordered_metadata(storage_view)
            cache_key = SnapshotTableArtifactCacheKey(
                row_layout_digest=row_layout_digest_of(
                    descriptor,
                    source_columns,
                    ordered_metadata,
                ),
                repository_id=request.repository_ref.repository_id,
            )
            cache_candidates[name] = (
                descriptor,
                source_columns,
                ordered_metadata,
                cache_key,
            )
        if cache_candidates:
            try:
                cached_row_refs = request.export_cache.lookup_many(
                    tuple(item[3] for item in cache_candidates.values())
                )
            except Exception:
                cached_row_refs = {}
    diagnostics: list[MaterializationDiagnostic] = []
    published: list[SnapshotTable] = []
    descriptors: list[SnapshotTableDescriptor] = []
    for name in sorted(binding_by_name, key=lambda item: item.encode("utf-8")):
        _checkpoint(request.context)
        catalog_table = indexed[name]
        storage_view = binding_by_name[name]
        if name in selected_set:
            cache_candidate = cache_candidates.get(name)
            cached_row_ref = (
                None if cache_candidate is None else cached_row_refs.get(cache_candidate[3])
            )
            table = None
            if cached_row_ref is not None and cache_candidate is not None and cache_store is not None:
                descriptor, source_columns, ordered_metadata, cache_key = cache_candidate
                try:
                    table = open_cached_snapshot_table(
                        cached_row_ref,
                        descriptor=descriptor,
                        source_columns=source_columns,
                        ordered_metadata=ordered_metadata,
                        effective_key_columns=descriptor.compare_key_columns,
                        store=cache_store,
                    )
                except (ArtifactPublishError, ManifestVerificationError):
                    try:
                        request.export_cache.discard_many((cache_key,))
                    except Exception:
                        pass
            if table is None:
                descriptor, table, table_diagnostics = _read_and_materialize_table(
                    request,
                    session,
                    catalog_table,
                    storage_view,
                    stage,
                    keep_rows=request.policy is MaterializationPolicy.READERS_REQUIRED,
                )
            else:
                descriptor = table.descriptor
                table_diagnostics = table.diagnostics
            identity = identities.get(name)
            if identity is not None and (
                descriptor.row_count != identity.row_count
                or descriptor.raw_content_digest != identity.raw_content_digest
            ):
                raise _Halt(
                    MaterializationDiagnosticCode.REPOSITORY_SNAPSHOT_DIGEST_MISMATCH,
                    "Repository table content does not match canonical metadata",
                    table=name,
                )
        else:
            identity = identities[name]
            descriptor = _describe_without_rows(
                request,
                catalog_table,
                identity,
                stage,
            )
            table = None
            table_diagnostics = ()
        descriptors.append(descriptor)
        diagnostics.extend(table_diagnostics)
        if table is not None:
            published.append(table)
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


def _describe_without_rows(
    request: RepositoryRefMaterializationRequest,
    catalog_table: RepositoryCatalogTable,
    identity: CanonicalTableIdentity,
    stage: MaterializationStage,
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


def _read_and_materialize_table(
    request: RepositoryRefMaterializationRequest,
    session: RepositoryRefSession,
    catalog_table: RepositoryCatalogTable,
    storage_view: StorageRuleView,
    stage: MaterializationStage,
    *,
    keep_rows: bool,
) -> tuple[SnapshotTableDescriptor, SnapshotTable | None, tuple[MaterializationDiagnostic, ...]]:
    table_name = canonicalize_identifier(catalog_table.table_name)
    try:
        reader = session.open_table_reader(catalog_table.table_name)
    except RepositoryProviderError as exc:
        if exc.retryable:
            raise
        raise _Halt(exc.code, exc.message, table=table_name) from exc
    diagnostics: list[MaterializationDiagnostic] = []
    encoded_rows: list[SourceRow] = []
    row_hashes: list[bytes] = []
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
    try:
        compare_keys = effective_key_columns(source_descriptor, compare_key_index(request.ruleset))
    except CompareKeyError as exc:
        reader.close()
        raise _Halt(
            MaterializationDiagnosticCode.COMPARE_KEY_UNKNOWN_COLUMN,
            str(exc),
            table=table_name,
        ) from exc
    schema_digest = compare_schema_digest(
        table_name,
        tuple(column.canonical_name for column in source_columns),
        compare_keys,
    )
    name_to_index = {column.canonical_name: index for index, column in enumerate(source_columns)}
    key_indexes = tuple(name_to_index[name] for name in compare_keys)
    seen_keys: set[tuple[bytes, ...]] = set()
    duplicate_key = False
    actual_count = 0
    try:
        for raw in reader.stream_rows():
            _checkpoint(request.context)
            try:
                encoded = encode_repository_row(
                    catalog_table.columns, raw, table=table_name
                )
            except ValueError as exc:
                raise _Halt(
                    MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
                    str(exc) or "repository row is malformed",
                    table=table_name,
                ) from exc
            diagnostics.extend(encoded.diagnostics)
            actual_count += 1
            row_hashes.append(row_content_hash(source_columns, encoded.cells))
            if key_indexes:
                key = tuple(
                    encode_cell_frame(source_columns[index], encoded.cells[index])
                    for index in key_indexes
                )
                if key in seen_keys:
                    duplicate_key = True
                else:
                    seen_keys.add(key)
            if keep_rows:
                encoded_rows.append(encoded.cells)
    except RepositoryProviderError as exc:
        if exc.retryable:
            raise
        raise _Halt(exc.code, exc.message, table=table_name) from exc
    except (CanonicalEncodingError, ValueError) as exc:
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_TABLE_READ_FAILED,
            str(exc) or "repository scalar encoding failed",
            table=table_name,
        ) from exc
    finally:
        reader.close()
    if catalog_table.row_count is not None and actual_count != catalog_table.row_count:
        _LOGGER.warning(
            "Repository catalog row count differs from streamed row count",
            extra={
                "event": "repository_row_count_mismatch",
                "diagnostic_code": MaterializationDiagnosticCode.REPOSITORY_ROW_COUNT_MISMATCH.value,
                "metric_name": "repository_row_count_mismatch_total",
                "metric_increment": 1,
                "repository_id": request.repository_ref.repository_id,
                "commit_id": request.repository_ref.ref,
                "table": table_name,
                "catalog_row_count": catalog_table.row_count,
                "streamed_row_count": actual_count,
            },
        )
        raise _Halt(
            MaterializationDiagnosticCode.REPOSITORY_ROW_COUNT_MISMATCH,
            "Repository catalog row count differs from streamed row count",
            table=table_name,
        )
    degraded_reason: DegradedReason | None = None
    if not compare_keys:
        degraded_reason = DegradedReason.KEYLESS
    elif duplicate_key:
        degraded_reason = DegradedReason.DUPLICATE_EFFECTIVE_KEY
        diagnostics.append(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode.DUPLICATE_EFFECTIVE_KEY,
                severity=DiagnosticSeverity.WARNING,
                message="duplicate effective key rows were preserved",
                table=table_name,
            )
        )
    descriptor = SnapshotTableDescriptor(
        table_name=table_name,
        display_table_name=source_descriptor.display_name,
        columns=tuple(
            SnapshotColumnDescriptor(
                name=column.canonical_name,
                display_name=column.display_name,
                nullable=column.nullable,
                scalar_type=column.sql_type,
            )
            for column in source_columns
        ),
        primary_key_columns=source_descriptor.primary_key_canonical_names,
        compare_key_columns=compare_keys,
        row_count=actual_count,
        materialization_stage=stage,
        compare_schema_digest=schema_digest,
        table_ruleset_version=request.table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=raw_content_digest_of(tuple(row_hashes)),
        degraded_reason=degraded_reason,
        diagnostics=tuple(diagnostics),
    )
    if not keep_rows:
        return descriptor, None, tuple(diagnostics)
    source_reader = MaterializedTableReader(source_descriptor, tuple(encoded_rows))
    ordered_metadata = _ordered_metadata(storage_view)
    return (
        descriptor,
        SnapshotTable(
            descriptor=descriptor,
            reader=BoundSnapshotTableReader(descriptor, source_reader),
            diagnostics=tuple(diagnostics),
            ordered_metadata=ordered_metadata,
        ),
        tuple(diagnostics),
    )


def _ordered_metadata(storage_view: StorageRuleView) -> SnapshotTableOrderedMetadata | None:
    if storage_view.ordered_policy is not OrderedPolicy.GID_NO_V1:
        return None
    return SnapshotTableOrderedMetadata(
        blank_provenance=BlankRowProvenance.CANONICAL_PSEUDO_GID
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
        export_cache=request.export_cache,
        repository_id=request.repository_ref.repository_id,
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
