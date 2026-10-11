"""Pure parsing helpers for the host-side real dump census."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy, TableStaticRole

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
    tables: tuple[tuple[str, tuple[tuple[int, ...], ...] | None], ...]
    duplicate_scan_status: str
    effective_key_scan_status: str
    scanned_table_count: int
    rule_skipped_table_count: int
    unresolved_tables: list[str]
    reader_unavailable_tables: list[str]
    duplicate_by_table: dict[str, int]
    exact_duplicate_extra_rows: int
    conflicting_extra_rows: int
    duplicate_details_by_table: dict[str, dict[str, object]]


_KEYED_ROWS_WITH_ONE_DUPLICATE = ((1, 10), (1, 10), (2, 20))

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
            exact_duplicate_extra_rows=1,
            conflicting_extra_rows=0,
            duplicate_details_by_table={
                "keyed": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 0,
                    "differing_columns": [],
                    "max_group_size": 2,
                }
            },
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
            exact_duplicate_extra_rows=1,
            conflicting_extra_rows=0,
            duplicate_details_by_table={
                "keyed": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 0,
                    "differing_columns": [],
                    "max_group_size": 2,
                }
            },
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
            exact_duplicate_extra_rows=1,
            conflicting_extra_rows=0,
            duplicate_details_by_table={
                "keyed": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 0,
                    "differing_columns": [],
                    "max_group_size": 2,
                }
            },
        ),
        id="reader-unavailable",
    ),
    pytest.param(
        KeyScanCoverageShape(
            tables=(
                ("all-identical", ((1, 10), (1, 10))),
                ("same-key-conflict", ((2, 20), (2, 21))),
                ("mixed-key-repeats", ((3, 30), (3, 30), (3, 31), (4, 40), (4, 41))),
                ("multi-column-conflict", ((6, 60, 600), (6, 61, 601))),
            ),
            duplicate_scan_status="complete",
            effective_key_scan_status="complete",
            scanned_table_count=4,
            rule_skipped_table_count=0,
            unresolved_tables=[],
            reader_unavailable_tables=[],
            duplicate_by_table={
                "all-identical": 1,
                "same-key-conflict": 1,
                "mixed-key-repeats": 3,
                "multi-column-conflict": 1,
            },
            exact_duplicate_extra_rows=2,
            conflicting_extra_rows=4,
            duplicate_details_by_table={
                "all-identical": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 0,
                    "differing_columns": [],
                    "max_group_size": 2,
                },
                "same-key-conflict": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 0,
                    "conflicting_extra_rows": 1,
                    "differing_columns": ["value"],
                    "max_group_size": 2,
                },
                "mixed-key-repeats": {
                    "key_columns": ["id"],
                    "key_source": "EXPLICIT_RULE",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 2,
                    "differing_columns": ["value"],
                    "max_group_size": 3,
                },
                "multi-column-conflict": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 0,
                    "conflicting_extra_rows": 1,
                    "differing_columns": ["state", "value"],
                    "max_group_size": 2,
                },
            },
        ),
        id="duplicate-classification-and-effective-key-source",
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
        policy = (
            CanonicalKeyPolicy.EXPLICIT
            if table_name == "mixed-key-repeats"
            else CanonicalKeyPolicy.DDL_PRIMARY_KEY
        )
        return SimpleNamespace(record=SimpleNamespace(static_role=role, canonical_key_policy=policy))

    def census_table(name: str, rows: tuple[tuple[int, ...], ...] | None) -> SimpleNamespace:
        reader = None
        column_names = ("id", "value", "state")
        column_count = 2
        if rows is not None:
            consumed = False
            column_count = len(rows[0]) if rows else 2

            def iter_rows() -> Iterator[tuple[int, ...]]:
                nonlocal consumed
                if consumed:
                    raise AssertionError("census must consume each table reader once")
                consumed = True
                return iter(rows)

            reader = SimpleNamespace(iter_rows=iter_rows)
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                table_name=name,
                primary_key_columns=("id",),
                columns=tuple(SimpleNamespace(name=column) for column in column_names[:column_count]),
            ),
            reader=reader,
        )

    monkeypatch.setattr(real_dump_census, "resolve_table_rule", resolve_rule)
    monkeypatch.setattr(
        real_dump_census,
        "derive_storage_rule_view",
        lambda record, _descriptor: SimpleNamespace(
            canonical_key_policy=record.canonical_key_policy,
            canonical_key_columns=("id",),
        ),
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
    assert result.exact_duplicate_extra_rows == shape.exact_duplicate_extra_rows
    assert result.conflicting_extra_rows == shape.conflicting_extra_rows
    assert result.duplicate_details_by_table == shape.duplicate_details_by_table


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
