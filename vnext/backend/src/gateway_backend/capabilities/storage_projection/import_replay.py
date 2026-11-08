"""Public Repository import schema facade; SQL encoding is owned by Rust."""

from __future__ import annotations

import json

from gateway_backend.capabilities.storage_projection.contracts import (
    MAX_REPLAY_SQL_BYTES,
    RepositoryImportArtifactInput,
)
from gateway_backend.capabilities.storage_projection.native import render_storage_schema_native
from gateway_backend.capabilities.snapshot_materialization import KernelExecutionContext, require_active_kernel_context


class ImportReplayError(ValueError):
    """Raised when repository import schema replay fails."""


def render_repository_import_schema_replay_sql(
    import_input: RepositoryImportArtifactInput,
    *,
    removed_tables: tuple[str, ...],
    context: KernelExecutionContext,
) -> bytes:
    active = require_active_kernel_context(context)
    if type(removed_tables) is not tuple:
        raise ImportReplayError("removed_tables must be a tuple")
    if any(type(name) is not str or not name for name in removed_tables):
        raise ImportReplayError("removed_tables must contain non-empty table names")
    if removed_tables != tuple(sorted(set(removed_tables), key=lambda name: name.encode("utf-8"))):
        raise ImportReplayError("removed_tables must contain sorted unique table names")
    if {table.name for table in import_input.tables} & set(removed_tables):
        raise ImportReplayError("removed_tables must be disjoint from import tables")
    names_bytes = sum(len(name.encode("utf-8")) for name in removed_tables)
    for table in import_input.tables:
        names_bytes += len(table.name.encode("utf-8"))
        names_bytes += sum(len(column.name.encode("utf-8")) + len(column.sql_type.encode("utf-8"))
                           for column in table.columns)
        names_bytes += sum(len(key.encode("utf-8")) for key in table.primary_key)
    # Reserve conversion graph and UTF8/escape expansion before making JSON.
    conversion = active.memory.reserve(names_bytes * 32 + 4096 * (len(import_input.tables) + 1))
    try:
        payload = json.dumps({
            "removed_tables": removed_tables,
            "tables": [{
                "name": table.name,
                "columns": [{"name": col.name, "sql_type": col.sql_type, "nullable": col.nullable}
                            for col in table.columns],
                "primary_key": table.primary_key,
            } for table in sorted(import_input.tables, key=lambda item: item.name.encode("utf-8"))],
        }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        limit = min(MAX_REPLAY_SQL_BYTES, len(payload) * 4 + 4096)
        try:
            return render_storage_schema_native(payload, active, limit)
        except ValueError as exc:
            raise ImportReplayError(str(exc)) from exc
    finally:
        conversion.close()
