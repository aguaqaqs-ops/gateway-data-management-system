"""Canonical storage projection. Publication lives in package.py and publish.py."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from gateway_shared_kernel import (
    CanonicalEncodingError,
    DeclaredType,
    DeclaredTypeKind,
    DigestRef,
    NullScalar,
    StringScalar,
    TypedScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    try_declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
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
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    ProjectionDiagnostic,
    ProjectionDiagnosticCode,
    ProjectionDiagnosticSeverity,
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
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    OrderedPolicy,
    StorageRuleView,
    TableRuleRecord,
    TableStaticRole,
    canonicalize_rule_identifier,
    resolve_table_rule,
)

_INT_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=32)
_UINT_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=32)
_VARCHAR_DECLARED_TYPE = DeclaredType(kind=DeclaredTypeKind.STRING)
_DECLARED_TYPES: dict[str, DeclaredType] = {
    "INT": _INT_DECLARED_TYPE,
    "INT UNSIGNED": _UINT_DECLARED_TYPE,
    "VARCHAR": _VARCHAR_DECLARED_TYPE,
}
_SIZED_VARCHAR = re.compile(r"^VARCHAR\(\d+\)$")


class _ProjectionFailed(Exception):
    def __init__(self, diagnostic: ProjectionDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


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


def _project_storage(request: ProjectionRequest) -> ProjectionResult:
    try:
        _raise_if_runtime(request)
        snapshot_digest = _shared_snapshot_digest(request)
        selected = _selected_inputs(request)
        projected: list[tuple[ProjectionTable, CanonicalizationManifestTable, RepositoryImportTable]] = []
        for item in selected:
            _raise_if_runtime(request)
            try:
                projected.append(_project_table(request, item, snapshot_digest))
            except _SkipTable:
                continue
        return _complete_result(request, snapshot_digest, projected)
    except _ProjectionFailed as exc:
        return ProjectionResult(
            status=ProjectionStatus.FAILED,
            tables=(),
            diagnostics=(exc.diagnostic,),
        )


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
    schema_columns, codecs, retained_indexes = _retained_schema(view, descriptor)
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
    for name in view.retained_columns:
        located = by_name.get(name)
        if located is None:
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "retained column is missing from the descriptor",
                    view.canonical_table,
                )
            )
        index, column = located
        codec = _codec_for(column, view)
        schema_columns.append(
            {
                "name": name,
                "nullable": codec.nullable,
                "sql_type": codec.sql_type,
            }
        )
        codecs[index] = codec
        retained_indexes.append(index)
    return schema_columns, codecs, tuple(retained_indexes)


def _resolve_declared_scalar_type(sql_type: str) -> DeclaredType | None:
    declared = try_declared_type_for_sql_spelling(sql_type)
    if declared is None:
        return None
    if declared.kind is DeclaredTypeKind.STRING:
        return _VARCHAR_DECLARED_TYPE
    if declared.kind is DeclaredTypeKind.SIGNED_INTEGER and declared.bits in {32, 64}:
        return declared
    if declared.kind is DeclaredTypeKind.UNSIGNED_INTEGER and declared.bits == 32:
        return declared
    return None


def _codec_for(column: SnapshotColumnDescriptor, view: StorageRuleView) -> CanonicalColumnCodec:
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
            )
        )
    try:
        enum_set = classify_enum_set_sql_type(sql_type)
    except CanonicalCellError as exc:
        raise _ProjectionFailed(
            _error(ProjectionDiagnosticCode.UNSUPPORTED_TABLE, str(exc), view.canonical_table)
        ) from exc
    if enum_set is not None:
        kind, labels = enum_set
        family: str = "enum" if kind == "ENUM" else "set"
        return CanonicalColumnCodec(
            sql_type=sql_type,
            nullable=column.nullable,
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
            )
        )
    return CanonicalColumnCodec(
        sql_type=sql_type,
        nullable=column.nullable,
        family="scalar",
        declared_type=declared,
    )


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
    content: ContentDigestBuilder,
    seen_keys: set[tuple[object, ...]],
) -> None:
    key = _row_key(row, key_indexes, view.canonical_table)
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


def _row_key(row: tuple[object, ...], key_indexes: tuple[int, ...], table_name: str) -> tuple[object, ...]:
    values: list[object] = []
    for index in key_indexes:
        cell = row[index]
        if not isinstance(cell, TypedScalar):
            raise _ProjectionFailed(
                _error(
                    ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
                    "key cell is not a typed scalar",
                    table_name,
                )
            )
        if isinstance(cell, NullScalar):
            raise _ProjectionFailed(
                _error(ProjectionDiagnosticCode.KEY_NULL, "canonical key contains null", table_name)
            )
        if isinstance(cell, StringScalar) and cell.text == "":
            raise _ProjectionFailed(
                _error(ProjectionDiagnosticCode.KEY_EMPTY, "canonical key contains an empty string", table_name)
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
) -> ProjectionDiagnostic:
    return ProjectionDiagnostic(
        code=code,
        severity=ProjectionDiagnosticSeverity.ERROR,
        message=message,
        table_name=table_name,
    )
