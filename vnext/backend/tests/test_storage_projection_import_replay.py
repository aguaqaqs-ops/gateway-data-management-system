"""Storage Projection schema replay owner tests."""

from __future__ import annotations

import pytest

from gateway_backend.capabilities.storage_projection import (
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    project_storage,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
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


def test_schema_replay_sql_includes_drop_create() -> None:
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
    replay_sql = render_repository_import_schema_replay_sql(result.import_input).decode("utf-8")
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE `net_cfg`" in replay_sql
    assert "INSERT INTO" not in replay_sql
