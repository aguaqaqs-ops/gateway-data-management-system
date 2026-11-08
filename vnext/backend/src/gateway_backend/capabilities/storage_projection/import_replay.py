"""Public Repository import schema facade; SQL encoding is owned by Rust."""

from __future__ import annotations

import json
from bisect import bisect_left

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
    # Python Unicode order and UTF8 byte order agree for valid scalar text.
    # Linear order checks and binary search avoid allocating a duplicate name
    # graph before the conversion reservation.
    previous: str | None = None
    for name in removed_tables:
        if previous is not None and name <= previous:
            raise ImportReplayError("removed_tables must contain sorted unique table names")
        previous = name
    for table in import_input.tables:
        index = bisect_left(removed_tables, table.name)
        if index < len(removed_tables) and removed_tables[index] == table.name:
            raise ImportReplayError("removed_tables must be disjoint from import tables")
    names_bytes_upper = sum(len(name) * 4 for name in removed_tables)
    columns_count = 0
    key_count = 0
    for table in import_input.tables:
        columns_count += len(table.columns)
        key_count += len(table.primary_key)
        names_bytes_upper += len(table.name) * 4
        names_bytes_upper += sum((len(column.name) + len(column.sql_type)) * 4
                           for column in table.columns)
        names_bytes_upper += sum(len(key) * 4 for key in table.primary_key)
    # Reserve conversion graph and UTF8/escape expansion before making JSON.
    conversion = active.memory.reserve(
        names_bytes_upper * 32 + 4096 * (len(import_input.tables) + columns_count + key_count + 1)
    )
    try:
        payload = json.dumps({
            "removed_tables": removed_tables,
            "tables": [{
                "name": table.name,
                "columns": [{"name": col.name, "sql_type": col.sql_type, "nullable": col.nullable}
                            for col in table.columns],
                "primary_key": table.primary_key,
            } for table in sorted(import_input.tables, key=lambda item: item.name)],
        }, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        # This is a memory envelope only: the SQL policy cap remains the
        # frozen 200 MiB. Names may repeat in DROP and CREATE and double in
        # identifier escaping; each declaration adds bounded punctuation.
        output_upper = min(
            MAX_REPLAY_SQL_BYTES,
            names_bytes_upper * 4
            + 256 * (len(removed_tables) + len(import_input.tables) + columns_count + key_count + 1),
        )
        try:
            return render_storage_schema_native(payload, active, MAX_REPLAY_SQL_BYTES, output_upper)
        except ValueError as exc:
            raise ImportReplayError(str(exc)) from exc
    finally:
        conversion.close()
