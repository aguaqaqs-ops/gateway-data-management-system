"""Ordinary keyed storage projection. Does not publish packages."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from gateway_shared_kernel import DateTimeScalar, DigestRef, Float32Scalar

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    DegradedReason,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection import (
    STORAGE_PROJECTION_VERSION,
    NeverCancel,
    ProjectionDiagnosticCode,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionResult,
    ProjectionStatus,
    ProjectionTableInput,
    project_canonical_table_set,
    project_storage,
)
from gateway_backend.capabilities.table_access.contracts import SourceRow
from gateway_backend.capabilities.table_access.contracts import ParserDiagnosticCode, TableAccessError
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    DroppedColumn,
    OrderedPolicy,
    SelectorPrecedenceClass,
    TableArtifactScope,
    TableCompareKeyMode,
    TableRuleRecord,
    TableRuleSelector,
    TableRuleSelectorKind,
    TableRulesetSnapshot,
    TableStaticRole,
    TableStorageDisposition,
    legacy_ignored_column_reason,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from tests.support.storage_projection import (
    FakeSnapshotTableReader,
    as_row,
    digest_ref,
    dummy_digest,
    int_cell,
    int_column,
    null_cell,
    table_input,
    typed_column,
    uint_cell,
    varchar_cell,
    varchar_column,
)
from tests.support.table_rules import net_cfg_record, snapshot_from_records

pytestmark = pytest.mark.unit

_NET_CFG_COLUMNS = (
    varchar_column("board"),
    int_column("link_no"),
    int_column("no", nullable=True),
)
_NET_CFG_ROWS = (
    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
    as_row(varchar_cell("eth1"), int_cell(2), int_cell(20)),
)
DC56_EXPLICIT_KEY_TABLES = (
    ("comm_user_data", ("data_key",)),
    ("forwardtbl_lst_cs", ("tbname",)),
    ("forwardtbl_lst_dz", ("tbname",)),
    ("forwardtbl_lst_qt", ("tbname",)),
    ("forwardtbl_lst_yc", ("tbname",)),
    ("forwardtbl_lst_yk", ("tbname",)),
    ("forwardtbl_lst_ym", ("tbname",)),
    ("forwardtbl_lst_yt", ("tbname",)),
    ("forwardtbl_lst_yx", ("tbname",)),
    ("mms_rp_cdc_index", ("idx",)),
    ("out_time_cfg", ("board", "link_no")),
)
TableInput = tuple[FakeSnapshotTableReader, ArtifactSourceBinding]


@dataclass
class FlagCancel:
    flag: bool = False

    def is_set(self) -> bool:
        return self.flag


def _request(
    *inputs: TableInput,
    ruleset: TableRulesetSnapshot | None = None,
    requested_tables: tuple[str, ...] | None = None,
    context: ProjectionInvocationContext | None = None,
) -> ProjectionRequest:
    tables = tuple(
        ProjectionTableInput(
            canonical_table=binding.descriptor.table_name,
            reader=reader,
            source_binding=binding,
        )
        for reader, binding in inputs
    )
    return ProjectionRequest(
        ruleset=ruleset or migrated_table_ruleset_snapshot(),
        storage_projection_version=STORAGE_PROJECTION_VERSION,
        tables=tables,
        context=context or ProjectionInvocationContext(cancel_requested=NeverCancel()),
        requested_tables=requested_tables,
    )


def _net_cfg_input(
    *,
    rows: tuple[SourceRow, ...] = _NET_CFG_ROWS,
    primary_key_columns: tuple[str, ...] = ("board", "link_no"),
    raw_content_digest: DigestRef | None = None,
    columns: tuple[SnapshotColumnDescriptor, ...] = _NET_CFG_COLUMNS,
    row_count: int | None = None,
    snapshot_digest: DigestRef | None = None,
    materialization_stage: MaterializationStage | None = None,
    degraded_reason: DegradedReason | None = None,
    iter_error: BaseException | None = None,
) -> TableInput:
    return table_input(
        "net_cfg",
        columns=columns,
        primary_key_columns=primary_key_columns,
        rows=rows,
        raw_content_digest=raw_content_digest,
        snapshot_digest=snapshot_digest,
        materialization_stage=materialization_stage,
        degraded_reason=degraded_reason,
        iter_error=iter_error,
        row_count=row_count,
    )


def _dc56_explicit_key_input(
    table_name: str,
    key_columns: tuple[str, ...],
    *,
    duplicate: bool,
    null_index: int = 0,
) -> TableInput:
    columns = tuple(varchar_column(name, nullable=True) for name in key_columns)
    values = tuple(varchar_cell("same") for _ in key_columns)
    first = as_row(*values)
    null_row = as_row(
        *(null_cell() if index == null_index else value for index, value in enumerate(values))
    )
    rows = (first, first) if duplicate else (null_row,)
    return table_input(
        table_name,
        columns=columns,
        primary_key_columns=(),
        rows=rows,
    )


def _codes(result: ProjectionResult) -> tuple[ProjectionDiagnosticCode, ...]:
    return tuple(item.code for item in result.diagnostics)


def test_fake_reader_reopen_returns_a_new_instance() -> None:
    reader, _binding = _net_cfg_input()
    reopened = reader.reopen()
    assert reopened is not reader
    assert tuple(reopened.iter_rows()) == tuple(reader.iter_rows())


def test_explicit_net_cfg_drops_ignored_column_and_repeats_key_in_manifest() -> None:
    result = project_storage(_request(_net_cfg_input()))
    assert result.status is ProjectionStatus.COMPLETE
    assert result.manifest is not None
    assert result.import_input is not None
    assert result.manifest.manifest_digest is not None
    assert result.import_input.canonicalization_manifest_digest == result.manifest.manifest_digest
    table = result.tables[0]
    assert table.storage_view.retained_columns == ("board", "link_no")
    assert "no" not in table.storage_view.retained_columns
    assert table.storage_view.canonical_key_columns == ("board", "link_no")
    assert table.storage_view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
    dropped = table.storage_view.dropped_columns
    assert dropped == (
        DroppedColumn(name="no", reason=legacy_ignored_column_reason(net_cfg_record().selector)),
    )
    manifest_table = result.manifest.tables[0]
    assert manifest_table.retained_columns == table.storage_view.retained_columns
    assert manifest_table.canonical_key_columns == table.storage_view.canonical_key_columns
    assert manifest_table.dropped_columns == dropped
    assert manifest_table.content_digest == table.content_digest
    import_table = result.import_input.tables[0]
    assert tuple(column.name for column in import_table.columns) == ("board", "link_no")
    assert import_table.primary_key == ("board", "link_no")
    assert table.row_count == 2
    assert result.manifest.source_artifact_digest == dummy_digest()


def test_ddl_fallback_unknown_table_uses_descriptor_primary_key() -> None:
    rows = (as_row(int_cell(1), varchar_cell("a")),)
    result = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(int_column("id"), varchar_column("name")),
                primary_key_columns=("id",),
                rows=rows,
            )
        )
    )
    assert result.status is ProjectionStatus.COMPLETE
    view = result.tables[0].storage_view
    assert view.canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
    assert view.canonical_key_columns == ("id",)
    assert view.retained_columns == ("id", "name")


def test_canonical_table_projection_emits_canonical_descriptor_and_reader() -> None:
    reader, binding = _net_cfg_input()
    raw = SnapshotTableSet(
        snapshot_id="raw-snapshot-1",
        snapshot_digest=binding.snapshot_digest,
        table_ruleset_version=1,
        tables=(SnapshotTable(descriptor=binding.descriptor, reader=reader),),
    )

    projected = project_canonical_table_set(raw, migrated_table_ruleset_snapshot())

    assert projected.status is ProjectionStatus.COMPLETE
    assert projected.manifest is not None
    assert projected.manifest.contract_version == "3.3.0"
    assert len(projected.tables) == 1
    canonical = projected.tables[0]
    assert canonical.descriptor.primary_key_columns == ("board", "link_no")
    assert tuple(column.name for column in canonical.descriptor.columns) == ("board", "link_no")
    assert all(not column.nullable for column in canonical.descriptor.columns)
    assert canonical.descriptor.raw_content_digest is not None
    assert canonical.reader is not None
    assert tuple(canonical.reader.iter_rows()) == tuple(row[:2] for row in _NET_CFG_ROWS)
    canonical.reader.close()


def test_composite_signal_projection_matches_s3_canonical_golden() -> None:
    columns = (
        typed_column("source_table", "VARCHAR(64)"),
        typed_column("point_gid", "BIGINT"),
        int_column("dev_addr"),
        int_column("device_gid"),
        typed_column("point_name", "TEXT"),
        typed_column("point_payload_json", "LONGTEXT"),
        typed_column("formula_digest", "TEXT", nullable=True),
        typed_column("formula_ast_json", "LONGTEXT", nullable=True),
    )
    rows = (
        as_row(
            varchar_cell("device_st"),
            int_cell(10),
            int_cell(65532),
            int_cell(1),
            varchar_cell("top"),
            varchar_cell('{"name":"top"}'),
            varchar_cell("sha256:" + "ab" * 32),
            varchar_cell('{"operator":"+","point":"top"}'),
        ),
    )
    reader, binding = table_input(
        "composite_signal_point",
        columns=columns,
        primary_key_columns=("source_table", "point_gid"),
        rows=rows,
    )

    result = project_storage(_request((reader, binding)))

    assert result.status is ProjectionStatus.COMPLETE
    assert result.manifest is not None
    assert result.import_input is not None
    projected = result.tables[0]
    import_table = result.import_input.tables[0]
    manifest_table = result.manifest.tables[0]
    assert projected.storage_view.retained_columns == (
        "source_table",
        "point_gid",
        "point_name",
        "formula_digest",
        "formula_ast_json",
    )
    assert import_table.primary_key == ("source_table", "point_gid")
    actual = {
        "canonical_columns": [
            {"name": column.name, "sql_type": column.sql_type, "nullable": column.nullable}
            for column in import_table.columns
        ],
        "canonical_key_columns": list(manifest_table.canonical_key_columns),
        "canonical_schema_digest": (
            None
            if manifest_table.canonical_schema_digest is None
            else manifest_table.canonical_schema_digest.value
        ),
        "content_digest": (
            None if manifest_table.content_digest is None else manifest_table.content_digest.value
        ),
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in manifest_table.dropped_columns
        ],
        "retained_columns": list(manifest_table.retained_columns),
        "row_count": import_table.row_count,
        "table_name": import_table.name,
    }
    golden_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "golden"
        / "storage-projection"
        / "composite-signal"
        / "canonical.json"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected


def test_canonical_projection_uses_storage_key_for_compare_keyless_table() -> None:
    reader, binding = _net_cfg_input(
        primary_key_columns=(),
        raw_content_digest=dummy_digest(),
        degraded_reason=DegradedReason.KEYLESS,
    )
    raw = SnapshotTableSet(
        snapshot_id="keyless-raw-snapshot",
        snapshot_digest=binding.snapshot_digest,
        table_ruleset_version=1,
        tables=(SnapshotTable(descriptor=binding.descriptor, reader=reader),),
    )

    projected = project_canonical_table_set(raw, migrated_table_ruleset_snapshot())

    assert projected.status is ProjectionStatus.COMPLETE
    assert len(projected.tables) == 1
    canonical = projected.tables[0]
    assert canonical.descriptor.degraded_reason is None
    assert canonical.descriptor.primary_key_columns == ("board", "link_no")
    assert canonical.reader is not None
    assert tuple(canonical.reader.iter_rows()) == tuple(row[:2] for row in _NET_CFG_ROWS)
    canonical.reader.close()


def test_storage_vocabulary_accepts_observed_unsigned_float_and_datetime_types() -> None:
    columns = (
        int_column("id"),
        typed_column("tiny_unsigned", "TINYINT UNSIGNED"),
        typed_column("small_unsigned", "SMALLINT UNSIGNED"),
        typed_column("temperature", "FLOAT"),
        typed_column("updated_at", "DATETIME"),
    )
    rows = (
        as_row(
            int_cell(1),
            uint_cell(2),
            uint_cell(300),
            Float32Scalar(bits_hex="3f800000"),
            DateTimeScalar(text="2026-10-11T12:34:56"),
        ),
    )

    result = project_storage(
        _request(
            table_input(
                "observed_types",
                columns=columns,
                primary_key_columns=("id",),
                rows=rows,
            )
        )
    )

    assert result.status is ProjectionStatus.COMPLETE
    assert result.import_input is not None
    assert tuple(column.sql_type for column in result.import_input.tables[0].columns) == (
        "INT",
        "TINYINT UNSIGNED",
        "SMALLINT UNSIGNED",
        "FLOAT",
        "DATETIME",
    )


def test_key_columns_reject_storage_types_that_repository_cannot_index() -> None:
    result = project_storage(
        _request(
            table_input(
                "text_key_table",
                columns=(typed_column("id", "TEXT"), varchar_column("payload")),
                primary_key_columns=("id",),
                rows=(as_row(varchar_cell("key"), varchar_cell("value")),),
            )
        )
    )

    assert result.status is ProjectionStatus.FAILED
    assert result.diagnostics[0].table_name == "text_key_table"
    assert result.diagnostics[0].column_name == "id"


def test_json_remains_fail_closed_without_dc12_evidence() -> None:
    result = project_storage(
        _request(
            table_input(
                "json_value_table",
                columns=(int_column("id"), typed_column("payload", "JSON")),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1), varchar_cell("{}")),),
            )
        )
    )

    assert result.status is ProjectionStatus.FAILED
    assert any(item.column_name == "payload" for item in result.diagnostics)


def test_projection_collects_schema_failures_for_every_table_and_column() -> None:
    def broken(name: str) -> TableInput:
        return table_input(
            name,
            columns=(
                int_column("id"),
                typed_column("bad_a", "DECIMAL(9,2)"),
                typed_column("bad_b", "BLOB"),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), int_cell(2), int_cell(3)),),
        )

    result = project_storage(_request(broken("broken_a"), broken("broken_b")))

    assert result.status is ProjectionStatus.FAILED
    assert {
        (item.table_name, item.column_name) for item in result.diagnostics
    } == {
        ("broken_a", "bad_a"),
        ("broken_a", "bad_b"),
        ("broken_b", "bad_a"),
        ("broken_b", "bad_b"),
    }


def test_explicit_canonical_key_ignores_source_ddl_primary_key_change() -> None:
    first = project_storage(_request(_net_cfg_input(primary_key_columns=("board",))))
    second = project_storage(_request(_net_cfg_input(primary_key_columns=("board", "link_no", "no"))))
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].storage_view.canonical_key_columns == ("board", "link_no")
    assert second.tables[0].storage_view.canonical_key_columns == ("board", "link_no")


def test_ddl_primary_key_policy_follows_source_primary_key_change() -> None:
    columns = (int_column("id"), varchar_column("name"))
    row = as_row(int_cell(1), varchar_cell("a"))
    first = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=columns,
                primary_key_columns=("id",),
                rows=(row,),
            )
        )
    )
    second = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=columns,
                primary_key_columns=("id", "name"),
                rows=(row,),
            )
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].storage_view.canonical_key_columns == ("id",)
    assert second.tables[0].storage_view.canonical_key_columns == ("id", "name")


KEY_FAULTS = (
    (
        "missing",
        ProjectionDiagnosticCode.KEY_MISSING,
        lambda: table_input(
            "unknown_widget",
            columns=(varchar_column("name"),),
            primary_key_columns=("id",),
            rows=(as_row(varchar_cell("a")),),
        ),
    ),
    (
        "duplicate",
        ProjectionDiagnosticCode.KEY_DUPLICATE,
        lambda: _net_cfg_input(
            rows=(
                as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
                as_row(varchar_cell("eth0"), int_cell(1), int_cell(11)),
            )
        ),
    ),
    (
        "null",
        ProjectionDiagnosticCode.KEY_NULL,
        lambda: _net_cfg_input(
            columns=(varchar_column("board", nullable=True), int_column("link_no"), int_column("no", nullable=True)),
            rows=(as_row(null_cell(), int_cell(1), int_cell(10)),),
        ),
    ),
    (
        "empty",
        ProjectionDiagnosticCode.KEY_EMPTY,
        lambda: _net_cfg_input(rows=(as_row(varchar_cell(""), int_cell(1), int_cell(10)),)),
    ),
)


@pytest.mark.parametrize(("label", "code", "factory"), KEY_FAULTS, ids=[item[0] for item in KEY_FAULTS])
def test_keyed_projection_rejects_invalid_keys(
    label: str,
    code: ProjectionDiagnosticCode,
    factory: Callable[[], TableInput],
) -> None:
    result = project_storage(_request(factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert result.import_input is None
    assert code in _codes(result)


@pytest.mark.parametrize(
    ("table_name", "key_columns"),
    DC56_EXPLICIT_KEY_TABLES,
    ids=[item[0] for item in DC56_EXPLICIT_KEY_TABLES],
)
@pytest.mark.parametrize(
    ("fault", "expected_code"),
    (
        ("duplicate", ProjectionDiagnosticCode.KEY_DUPLICATE),
        ("null", ProjectionDiagnosticCode.KEY_NULL),
    ),
)
def test_dc56_explicit_key_tables_fail_closed_on_duplicate_or_null(
    table_name: str,
    key_columns: tuple[str, ...],
    fault: str,
    expected_code: ProjectionDiagnosticCode,
) -> None:
    null_indexes = (0,) if fault == "duplicate" else tuple(range(len(key_columns)))
    for null_index in null_indexes:
        result = project_storage(
            _request(
                _dc56_explicit_key_input(
                    table_name,
                    key_columns,
                    duplicate=fault == "duplicate",
                    null_index=null_index,
                )
            )
        )

        assert result.status is ProjectionStatus.FAILED
        assert result.manifest is None
        assert result.import_input is None
        assert expected_code in _codes(result)


ROW_FAULTS = (
    (
        "row_count",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        lambda: _net_cfg_input(row_count=3),
    ),
    (
        "row_width",
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        lambda: _net_cfg_input(rows=(as_row(varchar_cell("eth0"), int_cell(1)),)),
    ),
)


@pytest.mark.parametrize(("label", "code", "factory"), ROW_FAULTS, ids=[item[0] for item in ROW_FAULTS])
def test_row_integrity_failures(
    label: str, code: ProjectionDiagnosticCode, factory: Callable[[], TableInput]
) -> None:
    result = project_storage(_request(factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert code in _codes(result)


def test_duplicate_keys_are_not_last_write_wins() -> None:
    result = project_storage(
        _request(
            _net_cfg_input(
                rows=(
                    as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),
                    as_row(varchar_cell("eth0"), int_cell(1), int_cell(99)),
                )
            )
        )
    )
    assert result.status is ProjectionStatus.FAILED
    assert ProjectionDiagnosticCode.KEY_DUPLICATE in _codes(result)


def test_reordered_rows_stay_complete_with_the_same_key_set() -> None:
    original = _NET_CFG_ROWS
    reordered = (_NET_CFG_ROWS[1], _NET_CFG_ROWS[0])
    first = project_storage(_request(_net_cfg_input(rows=original)))
    second = project_storage(_request(_net_cfg_input(rows=reordered)))
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].row_count == second.tables[0].row_count == 2


def test_dropped_column_source_change_does_not_change_r4_digests() -> None:
    first = project_storage(
        _request(
            _net_cfg_input(
                rows=(as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),),
                raw_content_digest=digest_ref("aa"),
            )
        )
    )
    second = project_storage(
        _request(
            _net_cfg_input(
                rows=(as_row(varchar_cell("eth0"), int_cell(1), int_cell(99)),),
                raw_content_digest=digest_ref("bb"),
            )
        )
    )
    assert first.status is ProjectionStatus.COMPLETE
    assert second.status is ProjectionStatus.COMPLETE
    assert first.tables[0].schema_digest == second.tables[0].schema_digest
    assert first.tables[0].content_digest == second.tables[0].content_digest
    assert first.manifest is not None
    assert second.manifest is not None
    first_input = _net_cfg_input(
        rows=(as_row(varchar_cell("eth0"), int_cell(1), int_cell(10)),),
        raw_content_digest=digest_ref("aa"),
    )
    second_input = _net_cfg_input(
        rows=(as_row(varchar_cell("eth0"), int_cell(1), int_cell(99)),),
        raw_content_digest=digest_ref("bb"),
    )
    assert first_input[1].descriptor.raw_content_digest != second_input[1].descriptor.raw_content_digest
    first_input[0].close()
    second_input[0].close()


def test_ignored_column_on_ddl_primary_key_fails_closed() -> None:
    selector = TableRuleSelector(kind=TableRuleSelectorKind.EXACT, value="custom_ddl")
    ruleset = snapshot_from_records(
        TableRuleRecord(
            selector=selector,
            precedence_class=SelectorPrecedenceClass.STANDARD_EXACT,
            static_role=TableStaticRole.STANDARD_DIFF,
            table_storage=TableStorageDisposition.PROJECT,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY,
            ordered_policy=OrderedPolicy.NONE,
            compare_key_mode=TableCompareKeyMode.RAW_PRIMARY_KEY,
            ignored_columns=("id",),
            dropped_columns=(DroppedColumn(name="id", reason=legacy_ignored_column_reason(selector)),),
            artifact_scope=TableArtifactScope.ALL_CHANGES,
        )
    )
    result = project_storage(
        _request(
            table_input(
                "custom_ddl",
                columns=(int_column("id"), varchar_column("name")),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1), varchar_cell("a")),),
            ),
            ruleset=ruleset,
        )
    )
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.RULESET_INVALID in _codes(result)


def test_snapshot_without_fallback_rejects_unclassified_table() -> None:
    result = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(int_column("id"),),
                primary_key_columns=("id",),
                rows=(as_row(int_cell(1)),),
            ),
            ruleset=snapshot_from_records(net_cfg_record()),
        )
    )
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.RULESET_INVALID in _codes(result)


TYPE_FAULTS = (
    (
        "missing_scalar_type",
        ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
        lambda: table_input(
            "unknown_widget",
            columns=(
                SnapshotColumnDescriptor(name="id", display_name="id", nullable=False),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1)),),
        ),
    ),
    (
        "set_sql_type",
        ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
        lambda: table_input(
            "unknown_widget",
            columns=(
                int_column("id"),
                SnapshotColumnDescriptor(
                    name="flags",
                    display_name="flags",
                    nullable=False,
                    scalar_type="SET",
                ),
            ),
            primary_key_columns=("id",),
            rows=(as_row(int_cell(1), varchar_cell("a")),),
        ),
    ),
)


@pytest.mark.parametrize(("label", "code", "factory"), TYPE_FAULTS, ids=[item[0] for item in TYPE_FAULTS])
def test_unsupported_schema_types(
    label: str, code: ProjectionDiagnosticCode, factory: Callable[[], TableInput]
) -> None:
    result = project_storage(_request(factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert code in _codes(result)


def test_requested_tables_projects_the_named_subset() -> None:
    skip_input = table_input(
        "device_model_table",
        columns=(int_column("id"),),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1)),),
    )
    result = project_storage(
        _request(_net_cfg_input(), skip_input, requested_tables=("net_cfg",))
    )
    assert result.status is ProjectionStatus.COMPLETE
    assert tuple(table.canonical_table for table in result.tables) == ("net_cfg",)
    assert result.manifest is not None
    assert tuple(table.name for table in result.manifest.tables) == ("net_cfg",)


def test_missing_requested_table_fails() -> None:
    result = project_storage(_request(_net_cfg_input(), requested_tables=("absent_table",)))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.REQUIRED_TABLE_FAILED in _codes(result)


def test_requested_skip_table_is_omitted_not_missing() -> None:
    result = project_storage(
        _request(_net_cfg_input(), requested_tables=("net_cfg", "device_model_table"))
    )
    assert result.status is ProjectionStatus.COMPLETE
    assert tuple(table.canonical_table for table in result.tables) == ("net_cfg",)


RUNTIME_FAULTS = (
    (
        "cancel",
        ProjectionDiagnosticCode.PROJECTION_CANCELLED,
        lambda: ProjectionInvocationContext(cancel_requested=FlagCancel(True)),
    ),
    (
        "deadline",
        ProjectionDiagnosticCode.PROJECTION_TIMEOUT,
        lambda: ProjectionInvocationContext(
            cancel_requested=NeverCancel(),
            deadline_monotonic=time.monotonic() - 1.0,
        ),
    ),
)


@pytest.mark.parametrize(("label", "code", "factory"), RUNTIME_FAULTS, ids=[item[0] for item in RUNTIME_FAULTS])
def test_cancel_and_deadline_fail_without_manifest(
    label: str,
    code: ProjectionDiagnosticCode,
    factory: Callable[[], ProjectionInvocationContext],
) -> None:
    reader, binding = _net_cfg_input()
    result = project_storage(_request((reader, binding), context=factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert result.import_input is None
    assert code in _codes(result)
    assert reader.closed is True


def test_reader_io_failure_does_not_publish() -> None:
    reader, binding = _net_cfg_input(iter_error=OSError("read failed"))
    result = project_storage(_request((reader, binding)))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.BINDING_INVALID in _codes(result)
    assert reader.closed is True


def test_reader_contract_failure_does_not_escape_projection() -> None:
    reader, binding = _net_cfg_input(
        iter_error=TableAccessError(ParserDiagnosticCode.READER_CLOSED, "reader closed")
    )
    result = project_storage(_request((reader, binding)))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert result.import_input is None
    assert ProjectionDiagnosticCode.BINDING_INVALID in _codes(result)
    assert reader.closed is True


def test_skip_table_is_omitted_and_version_manager_keeps_no() -> None:
    skip_input = table_input(
        "device_model_table",
        columns=(int_column("id"), int_column("no")),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1), int_cell(2)),),
    )
    browse = table_input(
        "version_manager",
        columns=(int_column("id"), int_column("no"), varchar_column("label")),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1), int_cell(7), varchar_cell("v1")),),
    )
    result = project_storage(_request(skip_input, browse, _net_cfg_input()))
    assert result.status is ProjectionStatus.COMPLETE
    names = tuple(table.canonical_table for table in result.tables)
    assert "device_model_table" not in names
    version = next(table for table in result.tables if table.canonical_table == "version_manager")
    assert version.storage_view.canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
    assert "no" in version.storage_view.retained_columns
    assert version.storage_view.canonical_key_columns == ("id",)


BINDING_FAULTS = (
    (
        "provisional",
        lambda: _net_cfg_input(materialization_stage=MaterializationStage.PROVISIONAL),
    ),
    (
        "table_failed",
        lambda: _net_cfg_input(
            raw_content_digest=dummy_digest(),
            degraded_reason=DegradedReason.TABLE_FAILED,
        ),
    ),
)


@pytest.mark.parametrize(("label", "factory"), BINDING_FAULTS, ids=[item[0] for item in BINDING_FAULTS])
def test_binding_rejects_provisional_and_failed_tables(
    label: str, factory: Callable[[], TableInput]
) -> None:
    result = project_storage(_request(factory()))
    assert result.status is ProjectionStatus.FAILED
    assert result.manifest is None
    assert ProjectionDiagnosticCode.BINDING_INVALID in _codes(result)


def test_mismatched_snapshot_digest_is_binding_invalid() -> None:
    first = _net_cfg_input()
    second = table_input(
        "version_manager",
        columns=(int_column("id"),),
        primary_key_columns=("id",),
        rows=(as_row(int_cell(1)),),
        snapshot_digest=digest_ref("22"),
    )
    result = project_storage(_request(first, second))
    assert result.status is ProjectionStatus.FAILED
    assert ProjectionDiagnosticCode.BINDING_INVALID in _codes(result)


def test_raw_primary_key_fallback_projects_keyless_rows_without_deduplicating() -> None:
    rows = (
        as_row(varchar_cell("repeat")),
        as_row(varchar_cell("other")),
        as_row(varchar_cell("repeat")),
    )
    result = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(varchar_column("name"),),
                primary_key_columns=(),
                rows=rows,
            )
        )
    )
    reordered = project_storage(
        _request(
            table_input(
                "unknown_widget",
                columns=(varchar_column("name"),),
                primary_key_columns=(),
                rows=(rows[2], rows[0], rows[1]),
            )
        )
    )

    assert result.status is ProjectionStatus.COMPLETE
    assert reordered.status is ProjectionStatus.COMPLETE
    assert result.manifest is not None
    assert reordered.manifest is not None
    assert result.import_input is not None
    assert result.manifest.tables[0].canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
    assert result.manifest.tables[0].canonical_key_columns == ()
    assert result.manifest.tables[0].canonical_row_count == len(rows)
    assert result.manifest.tables[0].content_digest == reordered.manifest.tables[0].content_digest
    assert result.import_input.tables[0].primary_key == ()
    assert result.import_input.tables[0].row_count == len(rows)


def test_device_cfg_keeps_strict_ddl_primary_key_requirement() -> None:
    result = project_storage(
        _request(
            table_input(
                "device_cfg",
                columns=(int_column("gid"), varchar_column("name")),
                primary_key_columns=(),
                rows=(as_row(int_cell(1), varchar_cell("device")),),
            )
        )
    )

    assert result.status is ProjectionStatus.FAILED
    assert ProjectionDiagnosticCode.KEY_MISSING in _codes(result)
