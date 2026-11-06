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


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise ImportReplayError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"
