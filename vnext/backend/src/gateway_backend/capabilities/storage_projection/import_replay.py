"""Public schema DDL and projection snapshot replay for RepositoryImportArtifact."""

from __future__ import annotations

from collections.abc import Mapping

from gateway_shared_kernel import (
    DateTimeScalar,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.storage_projection._digest import CanonicalColumnCodec
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifestTable,
    ImportReplayKeyedRow,
    ImportReplayTableSnapshot,
    ProjectionRequest,
    ProjectionResult,
    RepositoryImportArtifactInput,
    RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection.project import (
    _ProjectionFailed,
    _bound_descriptor,
    _retained_schema,
    materialize_canonical_source_rows,
)


class ImportReplayError(ValueError):
    """Raised when repository import schema replay fails."""


def render_repository_import_schema_replay_sql(
    import_input: RepositoryImportArtifactInput,
    *,
    removed_tables: tuple[str, ...],
) -> bytes:
    if type(removed_tables) is not tuple:
        raise ImportReplayError("removed_tables must be a tuple")
    if any(type(name) is not str or not name for name in removed_tables):
        raise ImportReplayError("removed_tables must contain non-empty table names")
    if removed_tables != tuple(
        sorted(set(removed_tables), key=lambda name: name.encode("utf-8"))
    ):
        raise ImportReplayError("removed_tables must contain sorted unique table names")
    import_table_names = {table.name for table in import_input.tables}
    if import_table_names & set(removed_tables):
        raise ImportReplayError("removed_tables must be disjoint from import tables")
    parts: list[bytes] = []
    for table_name in removed_tables:
        parts.append(_render_drop_table(table_name))
    for table in sorted(import_input.tables, key=lambda item: item.name.encode("utf-8")):
        parts.append(_render_drop_create_table(table))
    return b"".join(parts)


def build_import_projection_snapshots(
    request: ProjectionRequest,
    result: ProjectionResult,
) -> tuple[ImportReplayTableSnapshot, ...]:
    if result.manifest is None:
        raise ImportReplayError("projection manifest is required")
    inputs_by_name = {item.canonical_table: item for item in request.tables}
    manifest_by_name = {table.name: table for table in result.manifest.tables}
    projected_by_name = {table.canonical_table: table for table in result.tables}
    snapshots: list[ImportReplayTableSnapshot] = []
    for table_name in sorted(manifest_by_name):
        manifest_table = manifest_by_name[table_name]
        projected = projected_by_name.get(table_name)
        if projected is None:
            raise ImportReplayError(f"projected table {table_name} is missing")
        item = inputs_by_name.get(table_name)
        if item is None:
            raise ImportReplayError(f"projection input for {table_name} is missing")
        try:
            canonical_rows = materialize_canonical_source_rows(request, item, projected.storage_view)
        except _ProjectionFailed as exc:
            raise ImportReplayError(exc.diagnostic.message) from exc
        descriptor = _bound_descriptor(item, item.source_binding.snapshot_digest)
        _, codecs, retained_indexes = _retained_schema(projected.storage_view, descriptor)
        keyed_rows = _keyed_rows_from_canonical(
            canonical_rows,
            manifest_table=manifest_table,
            codecs=codecs,
            retained_indexes=retained_indexes,
        )
        snapshots.append(
            ImportReplayTableSnapshot(
                manifest_table=manifest_table,
                storage_view=projected.storage_view,
                rows=keyed_rows,
            )
        )
    return tuple(snapshots)


def _render_drop_create_table(table: RepositoryImportTable) -> bytes:
    name = _quote_identifier(table.name)
    column_defs: list[str] = []
    for column in table.columns:
        nullability = " NULL" if column.nullable else " NOT NULL"
        column_defs.append(f"{_quote_identifier(column.name)} {column.sql_type}{nullability}")
    if table.primary_key:
        keys = ", ".join(_quote_identifier(key) for key in table.primary_key)
        column_defs.append(f"PRIMARY KEY ({keys})")
    body = ", ".join(column_defs)
    return f"DROP TABLE IF EXISTS {name};\nCREATE TABLE {name} ({body});\n".encode("utf-8")


def _render_drop_table(table_name: str) -> bytes:
    return f"DROP TABLE IF EXISTS {_quote_identifier(table_name)};\n".encode("utf-8")


def _keyed_rows_from_canonical(
    canonical_rows: tuple[tuple[object, ...], ...],
    *,
    manifest_table: CanonicalizationManifestTable,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[ImportReplayKeyedRow, ...]:
    retained = manifest_table.retained_columns
    key_columns = manifest_table.canonical_key_columns
    keyed_rows: list[ImportReplayKeyedRow] = []
    for row in canonical_rows:
        image_columns = _image_columns_for_row(
            row,
            retained=retained,
            codecs=codecs,
            retained_indexes=retained_indexes,
        )
        image_by_name = {name: cell for name, cell in image_columns}
        key_pairs = tuple((column, dict(image_by_name[column])) for column in key_columns)
        keyed_rows.append(
            ImportReplayKeyedRow(
                key_columns=key_pairs,
                image_columns=image_columns,
            )
        )
    keyed_rows.sort(key=lambda item: _key_bytes_for_ordering(item.key_columns))
    return tuple(keyed_rows)


def _key_bytes_for_ordering(key_columns: tuple[tuple[str, dict[str, object]], ...]) -> bytes:
    parts: list[bytes] = []
    for _name, cell in key_columns:
        kind = cell.get("kind")
        if kind == "null":
            parts.append(b"\x00")
        elif kind == "unsigned-integer":
            parts.append(b"\x01" + str(cell.get("decimal", "")).encode("utf-8"))
        elif kind == "signed-integer":
            parts.append(b"\x02" + str(cell.get("decimal", "")).encode("utf-8"))
        elif kind == "string":
            parts.append(b"\x03" + str(cell.get("text", "")).encode("utf-8"))
        else:
            raise ImportReplayError("unsupported key cell for ordering")
    return b"".join(parts)


def _image_columns_for_row(
    row: tuple[object, ...],
    *,
    retained: tuple[str, ...],
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[tuple[str, dict[str, object]], ...]:
    index_by_retained_name = {
        retained_name: source_index
        for source_index, retained_name in zip(retained_indexes, retained, strict=True)
    }
    pairs: list[tuple[str, dict[str, object]]] = []
    for name in sorted(retained):
        source_index = index_by_retained_name[name]
        codec = codecs[source_index]
        cell = row[source_index]
        pairs.append((name, _mutation_cell(cell, codec)))
    return tuple(pairs)


def _mutation_cell(cell: object, codec: CanonicalColumnCodec) -> dict[str, object]:
    if isinstance(cell, NullScalar):
        return {"kind": "null"}
    if codec.family == "enum":
        if not isinstance(cell, StringScalar):
            raise ImportReplayError("ENUM cell must be a string scalar or null")
        return {"kind": "string", "text": cell.text}
    if codec.family == "set":
        members = getattr(cell, "members", None)
        if type(members) is not tuple:
            raise ImportReplayError("SET cell must expose members or be null")
        selected = [label for label in codec.labels if label in set(members)]
        return {"kind": "string", "text": ",".join(selected)}
    if isinstance(cell, UnsignedIntegerScalar):
        return {"kind": "unsigned-integer", "decimal": cell.decimal}
    if isinstance(cell, SignedIntegerScalar):
        return {"kind": "signed-integer", "decimal": cell.decimal}
    if isinstance(cell, Float32Scalar):
        return {"kind": "float32", "bits_hex": cell.bits_hex}
    if isinstance(cell, Float64Scalar):
        return {"kind": "float64", "bits_hex": cell.bits_hex}
    if isinstance(cell, StringScalar):
        return {"kind": "string", "text": cell.text}
    if isinstance(cell, DateTimeScalar):
        return {"kind": "datetime", "text": cell.text}
    raise ImportReplayError("unsupported canonical cell for mutation replay")


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise ImportReplayError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"
