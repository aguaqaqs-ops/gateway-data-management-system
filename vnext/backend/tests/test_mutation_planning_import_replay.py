"""Mutation Planning import replay owner tests."""

from __future__ import annotations

import pytest

from gateway_backend.capabilities.mutation_planning import (
    build_import_mutation_snapshots,
    render_import_mutation_dml,
)
from gateway_backend.capabilities.storage_projection import (
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionStatus,
    ProjectionTableInput,
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    build_import_projection_snapshots,
    project_storage,
    render_repository_import_schema_replay_sql,
)
from gateway_backend.capabilities.storage_projection._ordered import GID_PSEUDO_MIN
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from tests.support.storage_projection import (
    digest_ref,
    as_row,
    int_cell,
    int_column,
    null_cell,
    set_cell,
    set_column,
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


def test_import_replay_sql_includes_drop_create_and_inserts() -> None:
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
    projection_snapshots = build_import_projection_snapshots(
        _request(
            ProjectionTableInput(
                canonical_table="net_cfg",
                reader=reader.reopen(),
                source_binding=binding,
            )
        ),
        result,
    )
    snapshots = build_import_mutation_snapshots(projection_snapshots)
    replay_sql = (
        render_repository_import_schema_replay_sql(result.import_input, removed_tables=())
        + render_import_mutation_dml(
            result,
            snapshots,
            repository_base_digest=digest_ref("aa"),
            removed_tables=(),
        )
    ).decode("utf-8")
    assert "DROP TABLE IF EXISTS `net_cfg`" in replay_sql
    assert "CREATE TABLE `net_cfg`" in replay_sql
    assert "INSERT INTO `net_cfg`" in replay_sql


def test_import_replay_allocates_ordered_blank_gid() -> None:
    reader, binding = table_input(
        "b1_n1_iec104_syx_list",
        columns=(
            int_column("gid", nullable=True),
            int_column("no"),
            varchar_column("value"),
        ),
        primary_key_columns=("gid",),
        rows=(as_row(null_cell(), int_cell(1), varchar_cell("x")),),
    )
    request = _request(
        ProjectionTableInput(
            canonical_table="b1_n1_iec104_syx_list",
            reader=reader,
            source_binding=binding,
        )
    )
    result = project_storage(request)
    assert result.status is ProjectionStatus.COMPLETE
    projection_snapshots = build_import_projection_snapshots(
        _request(
            ProjectionTableInput(
                canonical_table="b1_n1_iec104_syx_list",
                reader=reader.reopen(),
                source_binding=binding,
            )
        ),
        result,
    )
    snapshots = build_import_mutation_snapshots(projection_snapshots)
    gid_cell = snapshots[0].rows[0].image.columns[0][1]
    assert gid_cell == {"kind": "unsigned-integer", "decimal": str(GID_PSEUDO_MIN)}
    replay_sql = render_import_mutation_dml(
        result,
        snapshots,
        repository_base_digest=digest_ref("aa"),
        removed_tables=(),
    ).decode("utf-8")
    assert f"VALUES ({GID_PSEUDO_MIN}, 1, 'x')" in replay_sql


def test_import_replay_supports_set_columns() -> None:
    reader, binding = table_input(
        "unknown_widget",
        columns=(
            int_column("id"),
            set_column("flags", "SET('x','y')"),
        ),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1), set_cell("y", "x")),),
    )
    request = _request(
        ProjectionTableInput(
            canonical_table="unknown_widget",
            reader=reader,
            source_binding=binding,
        )
    )
    result = project_storage(request)
    assert result.status is ProjectionStatus.COMPLETE
    projection_snapshots = build_import_projection_snapshots(
        _request(
            ProjectionTableInput(
                canonical_table="unknown_widget",
                reader=reader.reopen(),
                source_binding=binding,
            )
        ),
        result,
    )
    snapshots = build_import_mutation_snapshots(projection_snapshots)
    replay_sql = render_import_mutation_dml(
        result,
        snapshots,
        repository_base_digest=digest_ref("aa"),
        removed_tables=(),
    ).decode("utf-8")
    assert "INSERT INTO `unknown_widget`" in replay_sql
