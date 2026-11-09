"""Storage Projection schema replay owner tests."""

from __future__ import annotations

import json
from itertools import islice, product

from tests.support.native_projection import project_storage

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, KernelMemoryLimit, OperationMemoryBudget, kernel_execution_scope,
)
from gateway_backend.capabilities.storage_projection import (
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.storage_projection.native import render_storage_schema_native
from tests.support.storage_projection import (
    as_row,
    int_cell,
    int_column,
    table_input,
    varchar_cell,
    varchar_column,
)

pytestmark = pytest.mark.unit


def _request(*inputs: ProjectionTableInput) -> ProjectionRequest:
    return ProjectionRequest(
        ruleset=migrated_table_ruleset_snapshot(),
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        tables=inputs,
        context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
    )


def test_schema_replay_sql_includes_drop_create(
    operation_kernel_context: KernelExecutionContext,
) -> None:
    reader, binding = table_input(
        "net_cfg",
        columns=(
            varchar_column("board"),
            int_column("link_no"),
        ),
        primary_key_columns=("board", "link_no"),
        rows=(as_row(varchar_cell("eth0"), int_cell(1)),),
    )
    request = _request(
        ProjectionTableInput(
            canonical_table="net_cfg",
            reader=reader,
            source_binding=binding,
        )
    )
    result = project_storage(request)
    assert result.status is ProjectionStatus.COMPLETE
    assert result.import_input is not None
    replay_sql = render_repository_import_schema_replay_sql(
        result.import_input,
        removed_tables=(),
        context=operation_kernel_context,
    ).decode("utf-8")
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE `net_cfg`" in replay_sql
    assert "INSERT INTO" not in replay_sql


def test_schema_render_budget_rejection_releases_conversion_charge() -> None:
    small = KernelExecutionContext(OperationMemoryBudget(12 * 1024), NeverCancel(), 1)
    empty = RepositoryImportArtifactInput(1, raw_blob_digest(b""), ())
    with kernel_execution_scope(small, new_operation=True):
        with pytest.raises(KernelMemoryLimit):
            render_repository_import_schema_replay_sql(
                empty, removed_tables=("t",), context=small,
            )
        assert small.memory.used_bytes == 0
    assert small.memory.used_bytes == 0


def test_schema_sql_cap_counts_complete_drop_create_bytes(
    operation_kernel_context: KernelExecutionContext,
) -> None:
    import_input = RepositoryImportArtifactInput(1, raw_blob_digest(b""), (
        RepositoryImportTable("t", (RepositoryImportColumn("k", "INT", False),), ("k",), 0),
    ))
    expected = (b"DROP TABLE IF EXISTS `t`;\n"
                b"CREATE TABLE `t` (`k` INT NOT NULL, PRIMARY KEY (`k`));\n")
    assert render_repository_import_schema_replay_sql(
        import_input, removed_tables=(), context=operation_kernel_context,
    ) == expected
    payload = json.dumps({
        "removed_tables": [],
        "tables": [{"name": "t", "columns": [{"name": "k", "sql_type": "INT", "nullable": False}],
                    "primary_key": ["k"]}],
    }, separators=(",", ":")).encode()
    assert render_storage_schema_native(
        payload, operation_kernel_context, len(expected), len(expected),
    ) == expected
    with pytest.raises(ValueError, match="RESOURCE_EXCEEDED"):
        render_storage_schema_native(
            payload, operation_kernel_context, len(expected) - 1, len(expected),
        )


def test_many_short_removed_tables_render_below_frozen_sql_cap(
    operation_kernel_context: KernelExecutionContext,
) -> None:
    names = tuple("".join(chars) for chars in islice(
        product("0123456789abcdefghijklmnopqrstuvwxyz", repeat=3), 5000,
    ))
    empty = RepositoryImportArtifactInput(1, raw_blob_digest(b""), ())
    result = render_repository_import_schema_replay_sql(
        empty, removed_tables=names, context=operation_kernel_context,
    )
    expected_line_bytes = len(b"DROP TABLE IF EXISTS ``;\n") + 3
    assert len(result) == 5000 * expected_line_bytes
    assert result.count(b"DROP TABLE IF EXISTS ") == 5000
