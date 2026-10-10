"""Pure parsing helpers for the host-side real dump census."""

from __future__ import annotations

from types import SimpleNamespace
from typing import NamedTuple

import pytest

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_rules.contracts import TableStaticRole

from benchmarks import real_dump_census
from benchmarks.real_dump_census import _storage_column_type_key

CENSUS_STORAGE_COLUMN_TYPE_SHAPES: tuple[tuple[str, str], ...] = (
    ("INT(11) UNSIGNED", "INT UNSIGNED"),
    ("TINYINT UNSIGNED", "TINYINT UNSIGNED"),
    ("SMALLINT(5) UNSIGNED", "SMALLINT UNSIGNED"),
    ("DECIMAL(10, 2) UNSIGNED", "DECIMAL UNSIGNED"),
    ("VARCHAR(128)", "VARCHAR"),
    ("ENUM('a', 'b')", "ENUM"),
)


@pytest.mark.parametrize(
    ("sql_type", "expected"),
    CENSUS_STORAGE_COLUMN_TYPE_SHAPES,
)
@pytest.mark.unit
def test_census_storage_column_type_key_preserves_unsigned(
    sql_type: str,
    expected: str,
) -> None:
    assert _storage_column_type_key(sql_type) == expected


class KeyScanCoverageShape(NamedTuple):
    # (table name, rows); rows=None means the table has no reader.
    tables: tuple[tuple[str, tuple[tuple[int], ...] | None], ...]
    duplicate_scan_status: str
    effective_key_scan_status: str
    scanned_table_count: int
    rule_skipped_table_count: int
    unresolved_tables: list[str]
    reader_unavailable_tables: list[str]
    duplicate_by_table: dict[str, int]


_KEYED_ROWS_WITH_ONE_DUPLICATE = ((1,), (1,), (2,))

KEY_SCAN_COVERAGE_SHAPES = (
    pytest.param(
        KeyScanCoverageShape(
            tables=(("keyed", _KEYED_ROWS_WITH_ONE_DUPLICATE),),
            duplicate_scan_status="complete",
            effective_key_scan_status="complete",
            scanned_table_count=1,
            rule_skipped_table_count=0,
            unresolved_tables=[],
            reader_unavailable_tables=[],
            duplicate_by_table={"keyed": 1},
        ),
        id="all-tables-scanned",
    ),
    pytest.param(
        KeyScanCoverageShape(
            tables=(
                ("keyed", _KEYED_ROWS_WITH_ONE_DUPLICATE),
                ("unresolved", None),
                ("skipped", None),
            ),
            duplicate_scan_status="partial",
            effective_key_scan_status="partial",
            scanned_table_count=1,
            rule_skipped_table_count=1,
            unresolved_tables=["unresolved"],
            reader_unavailable_tables=[],
            duplicate_by_table={"keyed": 1},
        ),
        id="unresolved-and-rule-skipped-tables",
    ),
    pytest.param(
        KeyScanCoverageShape(
            tables=(
                ("keyed", _KEYED_ROWS_WITH_ONE_DUPLICATE),
                ("no_reader", None),
            ),
            duplicate_scan_status="partial",
            effective_key_scan_status="complete",
            scanned_table_count=1,
            rule_skipped_table_count=0,
            unresolved_tables=[],
            reader_unavailable_tables=["no_reader"],
            duplicate_by_table={"keyed": 1},
        ),
        id="reader-unavailable",
    ),
)


@pytest.mark.parametrize("shape", KEY_SCAN_COVERAGE_SHAPES)
@pytest.mark.unit
def test_duplicate_key_census_reports_coverage_per_table_outcome(
    monkeypatch: pytest.MonkeyPatch,
    shape: KeyScanCoverageShape,
) -> None:
    def resolve_rule(_ruleset: object, table_name: str, *, primary_key_columns: tuple[str, ...]) -> object:
        del primary_key_columns
        if table_name == "unresolved":
            raise ValueError("no rule")
        role = TableStaticRole.SKIP if table_name == "skipped" else TableStaticRole.STANDARD_DIFF
        return SimpleNamespace(record=SimpleNamespace(static_role=role))

    def census_table(name: str, rows: tuple[tuple[int], ...] | None) -> SimpleNamespace:
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                table_name=name,
                primary_key_columns=("id",),
                columns=(SimpleNamespace(name="id"),),
            ),
            reader=None if rows is None else SimpleNamespace(iter_rows=lambda: iter(rows)),
        )

    monkeypatch.setattr(real_dump_census, "resolve_table_rule", resolve_rule)
    monkeypatch.setattr(
        real_dump_census,
        "derive_storage_rule_view",
        lambda _record, _descriptor: SimpleNamespace(canonical_key_columns=("id",)),
    )

    result = real_dump_census._duplicate_and_effective_key_stats(
        table_set=SimpleNamespace(  # type: ignore[arg-type]
            tables=tuple(census_table(name, rows) for name, rows in shape.tables)
        ),
        ruleset=object(),
        diagnostic_mode=True,
        materialization_complete=True,
    )

    assert result.duplicate_scan_status == shape.duplicate_scan_status
    assert result.effective_key_scan_status == shape.effective_key_scan_status
    assert result.scanned_table_count == shape.scanned_table_count
    assert result.rule_skipped_table_count == shape.rule_skipped_table_count
    assert result.unresolved_tables == shape.unresolved_tables
    assert result.reader_unavailable_tables == shape.reader_unavailable_tables
    assert result.duplicate_by_table == shape.duplicate_by_table
    assert result.duplicate_extra_rows == sum(shape.duplicate_by_table.values())


@pytest.mark.unit
def test_sql_scan_fallback_keeps_tables_when_composite_stage_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table_set = SimpleNamespace(tables=())
    monkeypatch.setattr(
        real_dump_census,
        "materialize_sql_snapshot",
        lambda _request: SimpleNamespace(
            status=SnapshotMaterializationStatus.COMPLETE,
            table_set=table_set,
        ),
    )
    failed_business = SimpleNamespace(
        status=SnapshotMaterializationStatus.FAILED,
        table_set=None,
        diagnostics=(
            SimpleNamespace(code=MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED),
        ),
    )

    result = real_dump_census._sql_scan_source_after_composite_failure(
        failed_business,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        diagnostic_mode=True,
    )

    assert result[0] is not None
    assert result[0].tables == ()
    assert result[1:] == (True, "sql_snapshot_after_composite_failure")
