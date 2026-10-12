"""Canonical storage projection. Publication lives in package.py and publish.py."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import replace

from gateway_shared_kernel import (
    CanonicalEncodingError,
    DeclaredType,
    DeclaredTypeKind,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TypedScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.snapshot_materialization import (
    cell_count_key,
    compare_schema_digest as snapshot_compare_schema_digest,
    enum_set_labels_for_sql_spelling,
    fast_row_digest_of,
    fast_row_hash,
    raw_content_digest_of,
    row_content_hash,
    try_declared_type_for_sql_spelling,
    SourceCell,
    SourceColumnDescriptor,
    SourceRow,
    SqlLogicalType,
    SqlSetValue,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    ArtifactSourceBinding,
    BlankRowProvenance,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotColumnValueCounts,
    SnapshotTable,
    SnapshotTableArtifact,
    SnapshotTableDescriptor,
    SnapshotTableOrderedMetadata,
    SnapshotTableReader,
    SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection._digest import (
    CanonicalCellError,
    CanonicalColumnCodec,
    ContentDigestBuilder,
    compute_keyless_content_digest,
    compute_manifest_digest,
    compute_ordering_digest,
    compute_schema_digest,
    encode_canonical_cell,
    encode_row_cell_frame,
    classify_enum_set_sql_type,
)
from gateway_backend.capabilities.storage_projection._ordered import (
    OrderedProjectionError,
    project_ordered_rows,
)
from gateway_backend.capabilities.storage_projection._runtime import runtime_failure
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT,
    PACKAGE_VERSION,
    STORAGE_PROJECTION_VERSION,
    CanonicalProjectionResult,
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    MAX_DIAGNOSTICS,
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
    ProjectionInvocationContext,
    NeverCancel,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTable,
    ProjectionTableInput,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection.view import (
    StorageViewError,
    derive_storage_rule_view,
)
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    OrderedPolicy,
    StorageRuleView,
    TableRuleRecord,
    TableRulesetSnapshot,
    TableStaticRole,
    canonicalize_rule_identifier,
)

_UINT_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=32)
_VARCHAR_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)


class _ProjectionFailed(Exception):
    def __init__(self, diagnostic: ProjectionDiagnostic | tuple[ProjectionDiagnostic, ...]) -> None:
        diagnostics: tuple[ProjectionDiagnostic, ...]
        if isinstance(diagnostic, tuple):
            diagnostics = diagnostic
        else:
            diagnostics = (diagnostic,)
        if not diagnostics:
            raise ValueError("projection failure requires diagnostics")
        super().__init__(diagnostics[0].message)
        self.diagnostics = diagnostics
        self.diagnostic = diagnostics[0]


class _SkipTable(Exception):
    """Internal control: omit a SKIP table from the projection set."""


def project_storage(request: ProjectionRequest) -> ProjectionResult:
    readers = tuple(item.reader for item in request.tables)
    try:
        return _project_storage(request)
    finally:
        for reader in readers:
            try:
                reader.close()
            except Exception:
                continue


def project_canonical_table_set(
    raw_table_set: SnapshotTableSet,
    ruleset: TableRulesetSnapshot,
) -> CanonicalProjectionResult:
    """Project a raw snapshot table set into canonical descriptors and readers."""
    if type(raw_table_set) is not SnapshotTableSet or type(ruleset) is not TableRulesetSnapshot:
        return CanonicalProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "raw_table_set and ruleset must use their public contracts",
                ),
            ),
        )
    if ruleset.ruleset_digest is None:
        return CanonicalProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=(
                _error(ProjectionDiagnosticCode.RULESET_INVALID, "projection requires a complete ruleset_digest"),
            ),
        )

    inputs: list[ProjectionTableInput] = []
    diagnostics: list[ProjectionDiagnostic] = []
    source_by_name = {table.descriptor.table_name: table for table in raw_table_set.tables}
    for table in raw_table_set.tables:
        reader = table.reader
        if reader is None:
            if _is_skip_table(ruleset, table.descriptor):
                continue
            diagnostics.append(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "canonical projection requires a table reader",
                    table.descriptor.table_name,
                )
            )
            continue
        try:
            isolated = reader.reopen()
        except Exception:
            diagnostics.append(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "table reader could not be reopened",
                    table.descriptor.table_name,
                )
            )
            continue
        inputs.append(
            ProjectionTableInput(
                canonical_table=table.descriptor.table_name,
                reader=isolated,
                source_binding=ArtifactSourceBinding(
                    snapshot_digest=raw_table_set.snapshot_digest,
                    descriptor=table.descriptor,
                ),
                artifact=table.artifact,
            )
        )

    request = ProjectionRequest(
        ruleset=ruleset,
        storage_projection_version=ruleset.storage_projection_version,
        tables=tuple(inputs) or (_empty_projection_input(raw_table_set),),
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )
    projection = project_storage(request) if inputs else _empty_projection_result(request)
    if projection.status is ProjectionStatus.FAILED:
        diagnostics.extend(projection.diagnostics)
    if diagnostics:
        return CanonicalProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
        )
    assert projection.manifest is not None
    projected_by_name = {table.canonical_table: table for table in projection.tables}
    manifest_by_name = {table.name: table for table in projection.manifest.tables}
    canonical_tables: list[SnapshotTable] = []
    for name in sorted(projected_by_name, key=lambda item: item.encode("utf-8")):
        source = source_by_name[name]
        try:
            canonical_tables.append(
                _canonical_snapshot_table(
                    source,
                    projected_by_name[name],
                    manifest_by_name[name],
                    request=request,
                    snapshot_digest=raw_table_set.snapshot_digest,
                )
            )
        except _ProjectionFailed as exc:
            diagnostics.extend(exc.diagnostics)
    if diagnostics:
        for table in canonical_tables:
            if table.reader is not None:
                table.reader.close()
        return CanonicalProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=tuple(diagnostics[:MAX_DIAGNOSTICS]),
        )
    return CanonicalProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=tuple(canonical_tables),
        manifest=projection.manifest,
    )


def _empty_projection_input(table_set: SnapshotTableSet) -> ProjectionTableInput:
    descriptor = SnapshotTableDescriptor(
        table_name="__empty_projection__",
        display_table_name="__empty_projection__",
        columns=(),
        primary_key_columns=(),
        compare_key_columns=(),
        row_count=0,
        materialization_stage=MaterializationStage.FINAL,
        compare_schema_digest=snapshot_compare_schema_digest("__empty_projection__", (), ()),
        table_ruleset_version=table_set.table_ruleset_version,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=raw_content_digest_of(()),
    )
    reader = _EmptySnapshotTableReader(descriptor)
    return ProjectionTableInput(
        canonical_table=descriptor.table_name,
        reader=reader,
        source_binding=ArtifactSourceBinding(snapshot_digest=table_set.snapshot_digest, descriptor=descriptor),
    )


def _empty_projection_result(request: ProjectionRequest) -> ProjectionResult:
    ruleset_digest = request.ruleset.ruleset_digest
    if ruleset_digest is None:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.RULESET_INVALID, "projection requires a complete ruleset_digest")
        )
    manifest = CanonicalizationManifest(
        contract_version=CANONICALIZATION_MANIFEST_CONTRACT,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=request.ruleset.ruleset_id,
        ruleset_version=request.ruleset.ruleset_version,
        ruleset_digest=ruleset_digest,
        source_artifact_digest=request.tables[0].source_binding.snapshot_digest,
        tables=(),
    )
    digest = compute_manifest_digest(manifest)
    return ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=(),
        manifest=replace(manifest, manifest_digest=digest),
        import_input=RepositoryImportArtifactInput(
            package_version=PACKAGE_VERSION,
            canonicalization_manifest_digest=digest,
            tables=(),
        ),
    )


def _is_skip_table(ruleset: TableRulesetSnapshot, descriptor: SnapshotTableDescriptor) -> bool:
    try:
        resolved = resolve_table_rule(
            ruleset,
            descriptor.table_name,
            primary_key_columns=descriptor.primary_key_columns,
        )
    except ValueError:
        return False
    return resolved.record.static_role is TableStaticRole.SKIP


class _EmptySnapshotTableReader:
    def __init__(self, descriptor: SnapshotTableDescriptor) -> None:
        self._descriptor = descriptor
        self._closed = False
        self._iterated = False

    def descriptor(self) -> SnapshotTableDescriptor:
        if self._closed:
            raise ValueError("reader is closed")
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        if self._closed or self._iterated:
            raise ValueError("reader is closed or already consumed")
        self._iterated = True
        return iter(())

    def count_column_values(self, column_name: str) -> SnapshotColumnValueCounts:
        if self._closed:
            raise ValueError("reader is closed")
        return SnapshotColumnValueCounts(column_name=column_name, counts=(), total_row_count=0)

    def close(self) -> None:
        self._closed = True

    def reopen(self) -> SnapshotTableReader:
        if self._closed:
            raise ValueError("reader is closed")
        return _EmptySnapshotTableReader(self._descriptor)


def _canonical_snapshot_table(
    source: SnapshotTable,
    projected: ProjectionTable,
    manifest_table: CanonicalizationManifestTable,
    *,
    request: ProjectionRequest,
    snapshot_digest: DigestRef,
) -> SnapshotTable:
    source_reader = source.reader
    if source_reader is None:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "canonical projection requires a table reader",
                source.descriptor.table_name,
            )
        )
    schema_columns, codecs, retained_indexes = _retained_schema(
        projected.storage_view,
        source.descriptor,
    )
    source_columns_by_name = {
        canonicalize_rule_identifier(column.name): column for column in source.descriptor.columns
    }
    canonical_columns = tuple(
        SnapshotColumnDescriptor(
            name=str(column["name"]),
            display_name=source_columns_by_name[str(column["name"])].display_name,
            nullable=bool(column["nullable"]),
            scalar_type=str(column["sql_type"]),
        )
        for column in schema_columns
    )
    canonical_source_columns = _snapshot_source_columns(
        canonical_columns,
        table_name=source.descriptor.table_name,
    )
    try:
        isolated = source_reader.reopen()
    except Exception as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "table reader could not be reopened for canonical hashing",
                source.descriptor.table_name,
            )
        ) from exc
    canonical_request, canonical_input = _projection_request_for_reader(
        raw_reader=isolated,
        raw_descriptor=source.descriptor,
        ruleset=request.ruleset,
        context=request.context,
        snapshot_digest=snapshot_digest,
        artifact=source.artifact,
    )
    row_hashes: list[bytes] = []
    fast_hashes: list[bytes] = []
    observed_count = 0
    try:
        for row in _iter_canonical_rows(
            canonical_request,
            canonical_input,
            view=projected.storage_view,
            retained_indexes=retained_indexes,
            codecs=codecs,
        ):
            row_hashes.append(row_content_hash(canonical_source_columns, row))
            fast_hashes.append(fast_row_hash(canonical_source_columns, row))
            observed_count += 1
    except _ProjectionFailed:
        raise
    except Exception as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "table reader failed while hashing canonical rows",
                source.descriptor.table_name,
            )
        ) from exc
    finally:
        canonical_input.reader.close()
    if observed_count != manifest_table.canonical_row_count:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "canonical row count does not match the manifest",
                source.descriptor.table_name,
            )
        )
    key_columns = manifest_table.canonical_key_columns
    canonical_descriptor = SnapshotTableDescriptor(
        table_name=source.descriptor.table_name,
        display_table_name=source.descriptor.display_table_name,
        columns=canonical_columns,
        primary_key_columns=key_columns,
        compare_key_columns=key_columns,
        row_count=observed_count,
        materialization_stage=MaterializationStage.FINAL,
        compare_schema_digest=snapshot_compare_schema_digest(
            source.descriptor.table_name,
            tuple(column.name for column in canonical_columns),
            key_columns,
        ),
        table_ruleset_version=source.descriptor.table_ruleset_version,
        row_materialization_profile=source.descriptor.row_materialization_profile,
        scalar_encoding_version=source.descriptor.scalar_encoding_version,
        fast_row_digest=fast_row_digest_of(tuple(fast_hashes)),
        raw_content_digest=raw_content_digest_of(tuple(row_hashes)),
    )
    reader = _CanonicalProjectionReader(
        raw_reader=source_reader,
        descriptor=canonical_descriptor,
        raw_descriptor=source.descriptor,
        ruleset=request.ruleset,
        context=request.context,
        snapshot_digest=snapshot_digest,
        artifact=source.artifact,
        view=projected.storage_view,
        retained_indexes=retained_indexes,
        codecs=codecs,
        source_columns=canonical_source_columns,
    )
    ordered_metadata = None
    if projected.storage_view.ordered_policy is OrderedPolicy.GID_NO_V1:
        ordered_metadata = SnapshotTableOrderedMetadata(
            blank_provenance=BlankRowProvenance.CANONICAL_PSEUDO_GID
        )
    return SnapshotTable(
        descriptor=canonical_descriptor,
        reader=reader,
        ordered_metadata=ordered_metadata,
    )


def _snapshot_source_columns(
    columns: tuple[SnapshotColumnDescriptor, ...],
    *,
    table_name: str,
) -> tuple[SourceColumnDescriptor, ...]:
    result: list[SourceColumnDescriptor] = []
    for ordinal, column in enumerate(columns):
        spelling = column.scalar_type
        if spelling is None:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "canonical column is missing scalar_type",
                    table_name,
                    column.name,
                )
            )
        try:
            enum_set = enum_set_labels_for_sql_spelling(spelling)
        except ValueError as exc:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "canonical ENUM/SET declaration is invalid",
                    table_name,
                    column.name,
                )
            ) from exc
        if enum_set is not None and enum_set[0] == "SET":
            result.append(
                SourceColumnDescriptor(
                    display_name=column.display_name,
                    canonical_name=column.name,
                    ordinal=ordinal,
                    sql_type=spelling,
                    logical_type=SqlLogicalType.SET,
                    declared_type=None,
                    nullable=column.nullable,
                    enum_or_set_labels=enum_set[1],
                )
            )
            continue
        if enum_set is not None and enum_set[0] == "ENUM":
            result.append(
                SourceColumnDescriptor(
                    display_name=column.display_name,
                    canonical_name=column.name,
                    ordinal=ordinal,
                    sql_type=spelling,
                    logical_type=SqlLogicalType.ENUM,
                    declared_type=_VARCHAR_DECLARED_TYPE,
                    nullable=column.nullable,
                    enum_or_set_labels=enum_set[1],
                )
            )
            continue
        declared = try_declared_type_for_sql_spelling(spelling)
        if declared is None:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "canonical column type cannot be decoded",
                    table_name,
                    column.name,
                )
            )
        logical_type = SqlLogicalType.JSON if spelling.upper() == "JSON" else SqlLogicalType.STANDARD
        result.append(
            SourceColumnDescriptor(
                display_name=column.display_name,
                canonical_name=column.name,
                ordinal=ordinal,
                sql_type=spelling,
                logical_type=logical_type,
                declared_type=declared,
                nullable=column.nullable,
            )
        )
    return tuple(result)


def _projection_request_for_reader(
    *,
    raw_reader: SnapshotTableReader,
    raw_descriptor: SnapshotTableDescriptor,
    ruleset: TableRulesetSnapshot,
    context: ProjectionInvocationContext,
    snapshot_digest: DigestRef,
    artifact: SnapshotTableArtifact | None,
) -> tuple[ProjectionRequest, ProjectionTableInput]:
    projection_input = ProjectionTableInput(
        canonical_table=raw_descriptor.table_name,
        reader=raw_reader,
        source_binding=ArtifactSourceBinding(
            snapshot_digest=snapshot_digest,
            descriptor=raw_descriptor,
        ),
        artifact=artifact,
    )
    return (
        ProjectionRequest(
            ruleset=ruleset,
            storage_projection_version=ruleset.storage_projection_version,
            tables=(projection_input,),
            context=context,
        ),
        projection_input,
    )


def _iter_canonical_rows(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    *,
    view: StorageRuleView,
    retained_indexes: tuple[int, ...],
    codecs: Mapping[int, CanonicalColumnCodec],
) -> Iterator[SourceRow]:
    for row in materialize_canonical_source_rows(request, item, view):
        yield _canonicalize_row(row, retained_indexes, codecs, view)


def _canonicalize_row(
    row: tuple[object, ...],
    retained_indexes: tuple[int, ...],
    codecs: Mapping[int, CanonicalColumnCodec],
    view: StorageRuleView,
) -> SourceRow:
    cells: list[SourceCell] = []
    retained_names = view.retained_columns
    for name, index in zip(retained_names, retained_indexes, strict=True):
        cell = row[index]
        codec = codecs[index]
        if codec.family == "set" and not isinstance(cell, NullScalar):
            members = getattr(cell, "members", None)
            if type(members) is not tuple:
                raise _ProjectionFailed(
                    _error(
                        ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                        "SET cell must expose a members tuple or be null",
                        view.canonical_table,
                        name,
                    )
                )
            seen = set(members)
            cell = SqlSetValue(tuple(label for label in codec.labels if label in seen))
        elif (
            codec.declared_type is not None
            and codec.declared_type.kind is DeclaredTypeKind.UNSIGNED_INTEGER
            and isinstance(cell, SignedIntegerScalar)
        ):
            cell = UnsignedIntegerScalar(decimal=cell.decimal)
        elif codec.declared_type is not None and codec.declared_type.kind is DeclaredTypeKind.FLOAT32:
            if isinstance(cell, Float32Scalar) and cell.bits_hex.lower() == "80000000":
                cell = Float32Scalar(bits_hex="00000000")
        elif codec.declared_type is not None and codec.declared_type.kind is DeclaredTypeKind.FLOAT64:
            if isinstance(cell, Float64Scalar) and cell.bits_hex.lower() == "8000000000000000":
                cell = Float64Scalar(bits_hex="0000000000000000")
        try:
            encode_canonical_cell(cell, codec)
        except (CanonicalCellError, TypeError, CanonicalEncodingError) as exc:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "cell cannot be represented by its canonical column type",
                    view.canonical_table,
                    name,
                )
            ) from exc
        cells.append(cell)  # type: ignore[arg-type]
    return tuple(cells)


class _CanonicalProjectionReader:
    def __init__(
        self,
        *,
        raw_reader: SnapshotTableReader,
        descriptor: SnapshotTableDescriptor,
        raw_descriptor: SnapshotTableDescriptor,
        ruleset: TableRulesetSnapshot,
        context: ProjectionInvocationContext,
        snapshot_digest: DigestRef,
        artifact: SnapshotTableArtifact | None,
        view: StorageRuleView,
        retained_indexes: tuple[int, ...],
        codecs: Mapping[int, CanonicalColumnCodec],
        source_columns: tuple[SourceColumnDescriptor, ...],
    ) -> None:
        self._raw_reader = raw_reader
        self._descriptor = descriptor
        self._raw_descriptor = raw_descriptor
        self._ruleset = ruleset
        self._context = context
        self._snapshot_digest = snapshot_digest
        self._artifact = artifact
        self._view = view
        self._retained_indexes = retained_indexes
        self._codecs = dict(codecs)
        self._source_columns = source_columns
        self._closed = False
        self._iterated = False
        self._active_reader: SnapshotTableReader | None = None

    def descriptor(self) -> SnapshotTableDescriptor:
        self._ensure_open()
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        self._ensure_open()
        if self._iterated:
            raise ValueError("canonical projection reader is single-consumer")
        self._iterated = True
        return self._iterate()

    def count_column_values(self, column_name: str) -> SnapshotColumnValueCounts:
        self._ensure_open()
        index_by_name = {column.canonical_name: index for index, column in enumerate(self._source_columns)}
        normalized = canonicalize_rule_identifier(column_name)
        index = index_by_name.get(normalized)
        if index is None:
            raise ValueError("column is not present in the canonical descriptor")
        counts: dict[str | None, int] = {}
        reader = self.reopen()
        observed = 0
        try:
            for row in reader.iter_rows():
                key = cell_count_key(self._source_columns[index], row[index])
                counts[key] = counts.get(key, 0) + 1
                observed += 1
        finally:
            reader.close()
        return SnapshotColumnValueCounts(
            column_name=normalized,
            counts=tuple(sorted(counts.items(), key=lambda item: item[0] or "")),
            total_row_count=observed,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._active_reader is not None:
            self._active_reader.close()
            self._active_reader = None

    def reopen(self) -> SnapshotTableReader:
        self._ensure_open()
        return _CanonicalProjectionReader(
            raw_reader=self._raw_reader,
            descriptor=self._descriptor,
            raw_descriptor=self._raw_descriptor,
            ruleset=self._ruleset,
            context=self._context,
            snapshot_digest=self._snapshot_digest,
            artifact=self._artifact,
            view=self._view,
            retained_indexes=self._retained_indexes,
            codecs=self._codecs,
            source_columns=self._source_columns,
        )

    def _iterate(self) -> Iterator[SourceRow]:
        raw_reader = self._raw_reader.reopen()
        self._active_reader = raw_reader
        request, item = _projection_request_for_reader(
            raw_reader=raw_reader,
            raw_descriptor=self._raw_descriptor,
            ruleset=self._ruleset,
            context=self._context,
            snapshot_digest=self._snapshot_digest,
            artifact=self._artifact,
        )
        try:
            yield from _iter_canonical_rows(
                request,
                item,
                view=self._view,
                retained_indexes=self._retained_indexes,
                codecs=self._codecs,
            )
        finally:
            raw_reader.close()
            self._active_reader = None

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("canonical projection reader is closed")


def _project_storage(request: ProjectionRequest) -> ProjectionResult:
    try:
        _raise_if_runtime(request)
        snapshot_digest = _shared_snapshot_digest(request)
        selected = _selected_inputs(request)
    except _ProjectionFailed as exc:
        return ProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=exc.diagnostics[:MAX_DIAGNOSTICS],
        )
    projected: list[tuple[ProjectionTable, CanonicalizationManifestTable, RepositoryImportTable]] = []
    diagnostics: list[ProjectionDiagnostic] = []
    for item in selected:
        try:
            _raise_if_runtime(request)
            projected.append(_project_table(request, item, snapshot_digest))
        except _SkipTable:
            continue
        except _ProjectionFailed as exc:
            if exc.diagnostic.code in {
                ProjectionDiagnosticCode.PROJECTION_CANCELLED,
                ProjectionDiagnosticCode.PROJECTION_TIMEOUT,
            }:
                return ProjectionResult(
                    status=ProjectionStatus.FAILED,
                    tables=(),
                    diagnostics=(exc.diagnostic,),
                )
            remaining = MAX_DIAGNOSTICS - len(diagnostics)
            if remaining > 0:
                diagnostics.extend(exc.diagnostics[:remaining])
    if diagnostics:
        return ProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=tuple(diagnostics),
        )
    return _complete_result(request, snapshot_digest, projected)


def _complete_result(
    request: ProjectionRequest,
    snapshot_digest: DigestRef,
    projected: list[tuple[ProjectionTable, CanonicalizationManifestTable, RepositoryImportTable]],
) -> ProjectionResult:
    ruleset_digest = request.ruleset.ruleset_digest
    if ruleset_digest is None:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.RULESET_INVALID, "projection requires a complete ruleset_digest")
        )
    projected.sort(key=lambda item: item[0].canonical_table.encode("utf-8"))
    manifest = CanonicalizationManifest(
        contract_version=CANONICALIZATION_MANIFEST_CONTRACT,
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        ruleset_id=request.ruleset.ruleset_id,
        ruleset_version=request.ruleset.ruleset_version,
        ruleset_digest=ruleset_digest,
        source_artifact_digest=snapshot_digest,
        tables=tuple(item[1] for item in projected),
    )
    manifest_digest = compute_manifest_digest(manifest)
    recomputed = compute_manifest_digest(replace(manifest, manifest_digest=None))
    if manifest_digest != recomputed:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.DIGEST_MISMATCH, "manifest digest mismatch")
        )
    manifest = replace(manifest, manifest_digest=manifest_digest)
    import_input = RepositoryImportArtifactInput(
        package_version=PACKAGE_VERSION,
        canonicalization_manifest_digest=manifest_digest,
        tables=tuple(item[2] for item in projected),
    )
    return ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=tuple(item[0] for item in projected),
        manifest=manifest,
        import_input=import_input,
    )


def _shared_snapshot_digest(request: ProjectionRequest) -> DigestRef:
    digest = request.tables[0].source_binding.snapshot_digest
    for item in request.tables:
        if item.source_binding.snapshot_digest != digest:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.BINDING_INVALID,
                    "snapshot_digest must be shared by every input",
                    item.canonical_table,
                )
            )
    return digest


def _selected_inputs(request: ProjectionRequest) -> tuple[ProjectionTableInput, ...]:
    if request.requested_tables is None:
        return request.tables
    available = {item.canonical_table: item for item in request.tables}
    selected: list[ProjectionTableInput] = []
    for name in request.requested_tables:
        item = available.get(name)
        if item is not None:
            selected.append(item)
            continue
        if _is_skip(request, name):
            continue
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.REQUIRED_TABLE_FAILED,
                "requested table is missing",
                name,
            )
        )
    return tuple(selected)


def _is_skip(request: ProjectionRequest, table_name: str) -> bool:
    try:
        resolved = resolve_table_rule(request.ruleset, table_name, primary_key_columns=())
    except ValueError:
        return False
    return resolved.record.static_role is TableStaticRole.SKIP


def _project_table(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    snapshot_digest: DigestRef,
) -> tuple[ProjectionTable, CanonicalizationManifestTable, RepositoryImportTable]:
    descriptor = _bound_descriptor(item, snapshot_digest)
    try:
        resolved = resolve_table_rule(
            request.ruleset,
            item.canonical_table,
            primary_key_columns=descriptor.primary_key_columns,
        )
    except ValueError as exc:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.RULESET_INVALID, str(exc), item.canonical_table)
        ) from exc
    record = resolved.record
    if record.static_role is TableStaticRole.SKIP:
        raise _SkipTable
    if _unsupported_record(record):
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "table kind is not supported",
                item.canonical_table,
            )
        )
    try:
        view = derive_storage_rule_view(record, descriptor)
    except StorageViewError as exc:
        raise _ProjectionFailed(_error(exc.code, exc.message, item.canonical_table)) from exc
    if view is None:
        raise _SkipTable
    diagnostics = list(_key_type_diagnostics(view, descriptor))
    try:
        schema_columns, codecs, retained_indexes = _retained_schema(view, descriptor)
    except _ProjectionFailed as exc:
        diagnostics.extend(exc.diagnostics)
        schema_columns, codecs, retained_indexes = [], {}, ()
    if diagnostics:
        raise _ProjectionFailed(tuple(diagnostics))
    schema_digest = compute_schema_digest(
        columns=schema_columns,
        primary_key=view.canonical_key_columns,
    )
    if view.ordered_policy is OrderedPolicy.GID_NO_V1:
        content_digest, ordering_digest, row_count, gid_real, gid_pseudo = _project_ordered(
            request, item, descriptor, view, codecs, retained_indexes
        )
    elif view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS:
        content_digest, row_count = _project_keyless(
            request, item, descriptor, view, codecs, retained_indexes
        )
        ordering_digest = None
        gid_real = None
        gid_pseudo = None
    else:
        content_digest, row_count = _project_keyed(
            request, item, descriptor, view, codecs, retained_indexes
        )
        ordering_digest = None
        gid_real = None
        gid_pseudo = None
    projection_table = ProjectionTable(
        canonical_table=view.canonical_table,
        storage_view=view,
        row_count=row_count,
        schema_digest=schema_digest,
        content_digest=content_digest,
        ordering_digest=ordering_digest,
    )
    manifest_table = CanonicalizationManifestTable(
        name=view.canonical_table,
        source_row_count=descriptor.row_count,
        canonical_row_count=row_count,
        canonical_key_policy=view.canonical_key_policy,
        ordered_policy=view.ordered_policy,
        retained_columns=view.retained_columns,
        structural_columns=view.structural_columns,
        dropped_columns=view.dropped_columns,
        canonical_key_columns=view.canonical_key_columns,
        source_schema_digest=descriptor.compare_schema_digest,
        canonical_schema_digest=schema_digest,
        content_digest=content_digest,
        ordering_digest=ordering_digest,
        gid_real_count=gid_real,
        gid_pseudo_count=gid_pseudo,
    )
    import_table = RepositoryImportTable(
        name=view.canonical_table,
        columns=tuple(
            RepositoryImportColumn(
                name=str(column["name"]),
                sql_type=str(column["sql_type"]),
                nullable=bool(column["nullable"]),
            )
            for column in schema_columns
        ),
        primary_key=view.canonical_key_columns,
        row_count=row_count,
    )
    return projection_table, manifest_table, import_table


def _project_keyed(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[DigestRef, int]:
    key_indexes = _column_indexes(descriptor, view.canonical_key_columns)
    content = ContentDigestBuilder()
    seen_keys: set[tuple[object, ...]] = set()
    row_count = 0
    for row in _iter_source_rows(request, item, descriptor, view):
        _consume_keyed_row(
            row=row,
            view=view,
            codecs=codecs,
            retained_indexes=retained_indexes,
            key_indexes=key_indexes,
            key_names=view.canonical_key_columns,
            content=content,
            seen_keys=seen_keys,
        )
        row_count += 1
    _require_row_count(row_count, descriptor, view)
    return content.finish(), row_count


def _project_keyless(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[DigestRef, int]:
    frames: list[bytes] = []
    for row in _iter_source_rows(request, item, descriptor, view):
        frames.append(_encode_row_frame(row, retained_indexes, codecs, view))
    _require_row_count(len(frames), descriptor, view)
    content_digest = compute_keyless_content_digest(frames)
    if content_digest != compute_keyless_content_digest(tuple(frames)):
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.DIGEST_MISMATCH,
                "content digest mismatch",
                view.canonical_table,
            )
        )
    return content_digest, len(frames)


def _project_ordered(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[DigestRef, DigestRef, int, int, int]:
    rows = tuple(_iter_source_rows(request, item, descriptor, view))
    _require_row_count(len(rows), descriptor, view)
    gid_index, no_index = _ordered_indexes(descriptor, view)
    try:
        projected = project_ordered_rows(rows, gid_index=gid_index, no_index=no_index)
    except OrderedProjectionError as exc:
        raise _ProjectionFailed(_error(exc.code, exc.message, view.canonical_table)) from exc
    structural = set(view.structural_columns)
    content_indexes = tuple(
        index
        for index, name in zip(retained_indexes, view.retained_columns, strict=True)
        if name not in structural
    )
    content_rows = tuple(sorted(projected.rows, key=lambda row: _allocated_gid(row[gid_index])))
    content = ContentDigestBuilder()
    for row in content_rows:
        for index in content_indexes:
            content.add_cell_frame(_encode_cell(row[index], codecs[index], view))
    content_digest = content.finish()
    replay = ContentDigestBuilder()
    for row in content_rows:
        for index in content_indexes:
            replay.add_cell_frame(_encode_cell(row[index], codecs[index], view))
    if content_digest != replay.finish():
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.DIGEST_MISMATCH,
                "content digest mismatch",
                view.canonical_table,
            )
        )
    ordering_digest = compute_ordering_digest(
        ordered_policy=view.ordered_policy.value,
        rows=projected.facts,
    )
    if ordering_digest != compute_ordering_digest(
        ordered_policy=view.ordered_policy.value,
        rows=projected.facts,
    ):
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.DIGEST_MISMATCH,
                "ordering digest mismatch",
                view.canonical_table,
            )
        )
    return content_digest, ordering_digest, len(projected.rows), projected.real_count, projected.pseudo_count


def _bound_descriptor(item: ProjectionTableInput, snapshot_digest: DigestRef) -> SnapshotTableDescriptor:
    try:
        descriptor = item.reader.descriptor()
    except Exception as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "table reader descriptor failed",
                item.canonical_table,
            )
        ) from exc
    binding = item.source_binding
    if descriptor != binding.descriptor:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "reader descriptor must match source binding",
                item.canonical_table,
            )
        )
    if binding.snapshot_digest != snapshot_digest:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "snapshot_digest must be shared by every input",
                item.canonical_table,
            )
        )
    if descriptor.materialization_stage is not MaterializationStage.FINAL:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "projected tables require FINAL materialization",
                item.canonical_table,
            )
        )
    if descriptor.degraded_reason is not None or descriptor.raw_content_digest is None:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "projected tables must not be degraded",
                item.canonical_table,
            )
        )
    return descriptor


def _unsupported_record(record: TableRuleRecord) -> bool:
    return record.canonical_key_policy is CanonicalKeyPolicy.NONE


def _retained_schema(
    view: StorageRuleView,
    descriptor: SnapshotTableDescriptor,
) -> tuple[list[dict[str, object]], dict[int, CanonicalColumnCodec], tuple[int, ...]]:
    by_name = {
        canonicalize_rule_identifier(column.name): (index, column)
        for index, column in enumerate(descriptor.columns)
    }
    schema_columns: list[dict[str, object]] = []
    codecs: dict[int, CanonicalColumnCodec] = {}
    retained_indexes: list[int] = []
    diagnostics: list[ProjectionDiagnostic] = []
    non_null_columns = set(view.canonical_key_columns)
    if view.ordered_policy is OrderedPolicy.GID_NO_V1:
        non_null_columns.add(ORDERED_POSITION_COLUMN)
    for name in view.retained_columns:
        located = by_name.get(name)
        if located is None:
            diagnostics.append(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "retained column is missing from the descriptor",
                    view.canonical_table,
                    name,
                )
            )
            continue
        index, column = located
        try:
            codec = _codec_for(column, view, force_not_null=name in non_null_columns)
        except _ProjectionFailed as exc:
            diagnostics.extend(exc.diagnostics)
            continue
        schema_columns.append(
            {
                "name": name,
                "nullable": codec.nullable,
                "sql_type": codec.sql_type,
            }
        )
        codecs[index] = codec
        retained_indexes.append(index)
    if diagnostics:
        raise _ProjectionFailed(tuple(diagnostics))
    return schema_columns, codecs, tuple(retained_indexes)


def _resolve_declared_scalar_type(sql_type: str) -> DeclaredType | None:
    declared = try_declared_type_for_sql_spelling(sql_type)
    if declared is None:
        return None
    normalized = sql_type.strip().upper()
    if normalized == "JSON" or normalized.startswith("JSON "):
        return None
    if declared.kind is DeclaredTypeKind.STRING:
        return _VARCHAR_DECLARED_TYPE
    if declared.kind is DeclaredTypeKind.SIGNED_INTEGER and declared.bits in {8, 16, 24, 32, 64}:
        return declared
    if declared.kind is DeclaredTypeKind.UNSIGNED_INTEGER and declared.bits in {8, 16, 32}:
        return declared
    if declared.kind in {
        DeclaredTypeKind.FLOAT32,
        DeclaredTypeKind.FLOAT64,
        DeclaredTypeKind.DATETIME,
    }:
        return declared
    return None


def _codec_for(
    column: SnapshotColumnDescriptor,
    view: StorageRuleView,
    *,
    force_not_null: bool = False,
) -> CanonicalColumnCodec:
    name = canonicalize_rule_identifier(column.name)
    if view.ordered_policy is OrderedPolicy.GID_NO_V1 and name == ORDERED_IDENTITY_COLUMN:
        return CanonicalColumnCodec(
            sql_type="INT UNSIGNED",
            nullable=False,
            family="scalar",
            declared_type=_UINT_DECLARED_TYPE,
        )
    sql_type = column.scalar_type
    if sql_type is None:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "retained column is missing scalar_type",
                view.canonical_table,
                name,
            )
        )
    try:
        enum_set = classify_enum_set_sql_type(sql_type)
    except CanonicalCellError as exc:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.UNSUPPORTED_TABLE, str(exc), view.canonical_table, name)
        ) from exc
    if enum_set is not None:
        kind, labels = enum_set
        family: str = "enum" if kind == "ENUM" else "set"
        return CanonicalColumnCodec(
            sql_type=sql_type,
            nullable=column.nullable and not force_not_null,
            family=family,  # type: ignore[arg-type]
            declared_type=_VARCHAR_DECLARED_TYPE if kind == "ENUM" else None,
            labels=labels,
        )
    declared = _resolve_declared_scalar_type(sql_type)
    if declared is None:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "column scalar_type is not supported",
                view.canonical_table,
                name,
            )
        )
    return CanonicalColumnCodec(
        sql_type=sql_type,
        nullable=column.nullable and not force_not_null,
        family="scalar",
        declared_type=declared,
    )


def _key_type_diagnostics(
    view: StorageRuleView,
    descriptor: SnapshotTableDescriptor,
) -> tuple[ProjectionDiagnostic, ...]:
    columns = {canonicalize_rule_identifier(column.name): column for column in descriptor.columns}
    diagnostics: list[ProjectionDiagnostic] = []
    for name in view.canonical_key_columns:
        column = columns.get(name)
        if column is None or column.scalar_type is None:
            continue
        token = column.scalar_type.strip().upper()
        base = token.split("(", 1)[0].split(None, 1)[0]
        if base in {
            "JSON",
            "TINYTEXT",
            "TEXT",
            "MEDIUMTEXT",
            "LONGTEXT",
            "TINYBLOB",
            "BLOB",
            "MEDIUMBLOB",
            "LONGBLOB",
        }:
            diagnostics.append(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "canonical key column type cannot be indexed by Repository storage",
                    view.canonical_table,
                    name,
                )
            )
    return tuple(diagnostics)


def _column_indexes(descriptor: SnapshotTableDescriptor, names: tuple[str, ...]) -> tuple[int, ...]:
    by_name = {
        canonicalize_rule_identifier(column.name): index
        for index, column in enumerate(descriptor.columns)
    }
    return tuple(by_name[name] for name in names)


def _ordered_indexes(descriptor: SnapshotTableDescriptor, view: StorageRuleView) -> tuple[int, int]:
    by_name = {
        canonicalize_rule_identifier(column.name): index
        for index, column in enumerate(descriptor.columns)
    }
    try:
        return by_name[ORDERED_IDENTITY_COLUMN], by_name[ORDERED_POSITION_COLUMN]
    except KeyError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "ordered table requires gid and no columns",
                view.canonical_table,
            )
        ) from exc


def _iter_source_rows(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
) -> list[tuple[object, ...]]:
    try:
        rows: list[tuple[object, ...]] = []
        for row in item.reader.iter_rows():
            _raise_if_runtime(request)
            if type(row) is not tuple or len(row) != len(descriptor.columns):
                raise _ProjectionFailed(
                    _error(
                        ProjectionDiagnosticCode.ROW_INTEGRITY,
                        "row width does not match the descriptor",
                        view.canonical_table,
                    )
                )
            rows.append(row)
        return rows
    except _ProjectionFailed:
        raise
    except Exception as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "table reader failed",
                view.canonical_table,
            )
        ) from exc


def _require_row_count(row_count: int, descriptor: SnapshotTableDescriptor, view: StorageRuleView) -> None:
    if row_count != descriptor.row_count:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "row count does not match the source descriptor",
                view.canonical_table,
            )
        )


def _consume_keyed_row(
    *,
    row: tuple[object, ...],
    view: StorageRuleView,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
    key_indexes: tuple[int, ...],
    key_names: tuple[str, ...],
    content: ContentDigestBuilder,
    seen_keys: set[tuple[object, ...]],
) -> None:
    key = _row_key(row, key_indexes, key_names, view.canonical_table)
    if key in seen_keys:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.KEY_DUPLICATE,
                "canonical key is not unique",
                view.canonical_table,
            )
        )
    seen_keys.add(key)
    for index in retained_indexes:
        content.add_cell_frame(_encode_cell(row[index], codecs[index], view))


def _encode_row_frame(
    row: tuple[object, ...],
    retained_indexes: tuple[int, ...],
    codecs: Mapping[int, CanonicalColumnCodec],
    view: StorageRuleView,
) -> bytes:
    try:
        return encode_row_cell_frame(row, retained_indexes, codecs)
    except CanonicalCellError as exc:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.UNSUPPORTED_TABLE, str(exc), view.canonical_table)
        ) from exc
    except TypeError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "cell is not a typed scalar",
                view.canonical_table,
            )
        ) from exc
    except CanonicalEncodingError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "cell encoding failed",
                view.canonical_table,
            )
        ) from exc
    except OSError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "content digest write failed",
                view.canonical_table,
            )
        ) from exc


def _encode_cell(cell: object, codec: CanonicalColumnCodec, view: StorageRuleView) -> bytes:
    try:
        return encode_canonical_cell(cell, codec)
    except CanonicalCellError as exc:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.UNSUPPORTED_TABLE, str(exc), view.canonical_table)
        ) from exc
    except TypeError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "cell is not a typed scalar",
                view.canonical_table,
            )
        ) from exc
    except CanonicalEncodingError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                "cell encoding failed",
                view.canonical_table,
            )
        ) from exc
    except OSError as exc:
        raise _ProjectionFailed(
            _error(
                ProjectionDiagnosticCode.BINDING_INVALID,
                "content digest write failed",
                view.canonical_table,
            )
        ) from exc


def materialize_canonical_source_rows(
    request: ProjectionRequest,
    item: ProjectionTableInput,
    view: StorageRuleView,
) -> tuple[tuple[object, ...], ...]:
    """Return owner-canonicalized source rows for import replay materialization."""
    snapshot_digest = item.source_binding.snapshot_digest
    descriptor = _bound_descriptor(item, snapshot_digest)
    _, _, retained_indexes = _retained_schema(view, descriptor)
    if view.ordered_policy is OrderedPolicy.GID_NO_V1:
        rows = tuple(_iter_source_rows(request, item, descriptor, view))
        _require_row_count(len(rows), descriptor, view)
        gid_index, no_index = _ordered_indexes(descriptor, view)
        try:
            projected = project_ordered_rows(rows, gid_index=gid_index, no_index=no_index)
        except OrderedProjectionError as exc:
            raise _ProjectionFailed(_error(exc.code, exc.message, view.canonical_table)) from exc
        content_rows = tuple(
            sorted(projected.rows, key=lambda row: _allocated_gid(row[gid_index]))
        )
        return content_rows
    rows = tuple(_iter_source_rows(request, item, descriptor, view))
    _require_row_count(len(rows), descriptor, view)
    return rows


def _allocated_gid(cell: object) -> int:
    if not isinstance(cell, UnsignedIntegerScalar):
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.ROW_INTEGRITY, "projected gid must be unsigned")
        )
    return int(cell.decimal, 10)


def _row_key(
    row: tuple[object, ...],
    key_indexes: tuple[int, ...],
    key_names: tuple[str, ...],
    table_name: str,
) -> tuple[object, ...]:
    values: list[object] = []
    for index, key_name in zip(key_indexes, key_names, strict=True):
        cell = row[index]
        if not isinstance(cell, TypedScalar):
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "key cell is not a typed scalar",
                    table_name,
                    key_name,
                )
            )
        if isinstance(cell, NullScalar):
            raise _ProjectionFailed(
                _error(ProjectionDiagnosticCode.KEY_NULL, "canonical key contains null", table_name, key_name)
            )
        if isinstance(cell, StringScalar) and cell.text == "":
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.KEY_EMPTY,
                    "canonical key contains an empty string",
                    table_name,
                    key_name,
                )
            )
        values.append(cell)
    return tuple(values)


def _raise_if_runtime(request: ProjectionRequest) -> None:
    diagnostic = runtime_failure(request.context)
    if diagnostic is not None:
        raise _ProjectionFailed(diagnostic)


def _error(
    code: ProjectionDiagnosticCode,
    message: str,
    table_name: str | None = None,
    column_name: str | None = None,
) -> ProjectionDiagnostic:
    return ProjectionDiagnostic(
        code=code,
        severity=ProjectionDiagnosticSeverity.ERROR,
        message=message,
        table_name=table_name,
        column_name=column_name,
    )
