"""Pure parsing helpers for the host-side real dump census."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.storage_projection.contracts import ProjectionDiagnosticCode
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    OrderedPolicy,
    TableStaticRole,
)
from gateway_shared_kernel import NullScalar, SignedIntegerScalar, StringScalar

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
    tables: tuple[tuple[str, tuple[tuple[object, ...], ...] | None], ...]
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
            tables=(("nonordered-blank-key", ((NullScalar(), 10), (NullScalar(), 10))),),
            duplicate_scan_status="complete",
            effective_key_scan_status="complete",
            scanned_table_count=1,
            rule_skipped_table_count=0,
            unresolved_tables=[],
            reader_unavailable_tables=[],
            duplicate_by_table={"nonordered-blank-key": 1},
            exact_duplicate_extra_rows=1,
            conflicting_extra_rows=0,
            duplicate_details_by_table={
                "nonordered-blank-key": {
                    "key_columns": ["id"],
                    "key_source": "DDL_PRIMARY_KEY",
                    "exact_duplicate_extra_rows": 1,
                    "conflicting_extra_rows": 0,
                    "differing_columns": [],
                    "max_group_size": 2,
                }
            },
        ),
        id="nonordered-blank-key-keeps-existing-fingerprint",
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

    def census_table(name: str, rows: tuple[tuple[object, ...], ...] | None) -> SimpleNamespace:
        reader = None
        column_names = ("id", "value", "state")
        column_count = 2
        if rows is not None:
            consumed = False
            column_count = len(rows[0]) if rows else 2

            def iter_rows() -> Iterator[tuple[object, ...]]:
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
            ordered_policy=OrderedPolicy.NONE,
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
    assert result.ordered_projection_by_table == {}


class OrderedGidCensusShape(NamedTuple):
    rows: tuple[tuple[object, ...], ...]
    duplicate_extra_rows: int
    exact_duplicate_extra_rows: int
    conflicting_extra_rows: int
    duplicate_details: dict[str, object]
    projection_status: str
    diagnostic_code: str | None
    diagnostic_message: str | None
    real_gid_count: int
    pseudo_gid_count: int
    blank_gid_rows: int
    unparseable_gid_rows: int


ORDERED_GID_CENSUS_SHAPES = (
    pytest.param(
        OrderedGidCensusShape(
            rows=(
                (NullScalar(), SignedIntegerScalar("1"), StringScalar("first blank")),
                (StringScalar(""), SignedIntegerScalar("2"), StringScalar("second blank")),
                (SignedIntegerScalar("0"), SignedIntegerScalar("3"), StringScalar("third blank")),
            ),
            duplicate_extra_rows=0,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=0,
            duplicate_details={},
            projection_status="COMPLETE",
            diagnostic_code=None,
            diagnostic_message=None,
            real_gid_count=0,
            pseudo_gid_count=3,
            blank_gid_rows=3,
            unparseable_gid_rows=0,
        ),
        id="null-empty-and-zero-gids-are-pseudo",
    ),
    pytest.param(
        OrderedGidCensusShape(
            rows=(
                (NullScalar(), SignedIntegerScalar("1"), StringScalar("blank one")),
                (StringScalar(""), SignedIntegerScalar("2"), StringScalar("blank two")),
                (SignedIntegerScalar("9"), SignedIntegerScalar("3"), StringScalar("same")),
                (SignedIntegerScalar("9"), SignedIntegerScalar("4"), StringScalar("same")),
            ),
            duplicate_extra_rows=1,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=1,
            duplicate_details={
                "key_columns": ["gid"],
                "key_source": "EXPLICIT_RULE",
                "exact_duplicate_extra_rows": 0,
                "conflicting_extra_rows": 1,
                "differing_columns": ["no"],
                "max_group_size": 2,
            },
            projection_status="FAILED",
            diagnostic_code=ProjectionDiagnosticCode.KEY_DUPLICATE.value,
            diagnostic_message="canonical key is not unique",
            real_gid_count=2,
            pseudo_gid_count=0,
            blank_gid_rows=2,
            unparseable_gid_rows=0,
        ),
        id="mixed-blanks-and-real-gid-duplicate",
    ),
    pytest.param(
        OrderedGidCensusShape(
            rows=(
                (SignedIntegerScalar("1"), SignedIntegerScalar("1"), StringScalar("real")),
                (NullScalar(), SignedIntegerScalar("3"), StringScalar("blank")),
            ),
            duplicate_extra_rows=0,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=0,
            duplicate_details={},
            projection_status="FAILED",
            diagnostic_code=ProjectionDiagnosticCode.ROW_INTEGRITY.value,
            diagnostic_message="ordered no must be the continuous range 1..N",
            real_gid_count=1,
            pseudo_gid_count=0,
            blank_gid_rows=1,
            unparseable_gid_rows=0,
        ),
        id="noncontinuous-no",
    ),
    pytest.param(
        OrderedGidCensusShape(
            rows=(
                (SignedIntegerScalar("1"), SignedIntegerScalar("1"), StringScalar("first")),
                (SignedIntegerScalar("2"), SignedIntegerScalar("1"), StringScalar("second")),
            ),
            duplicate_extra_rows=0,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=0,
            duplicate_details={},
            projection_status="FAILED",
            diagnostic_code=ProjectionDiagnosticCode.ROW_INTEGRITY.value,
            diagnostic_message="ordered no is not unique",
            real_gid_count=2,
            pseudo_gid_count=0,
            blank_gid_rows=0,
            unparseable_gid_rows=0,
        ),
        id="duplicate-no",
    ),
    pytest.param(
        OrderedGidCensusShape(
            rows=(
                (
                    SignedIntegerScalar("4000000000"),
                    SignedIntegerScalar("1"),
                    StringScalar("reserved"),
                ),
            ),
            duplicate_extra_rows=0,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=0,
            duplicate_details={},
            projection_status="FAILED",
            diagnostic_code=ProjectionDiagnosticCode.ROW_INTEGRITY.value,
            diagnostic_message="source gid is in the reserved pseudo range",
            real_gid_count=0,
            pseudo_gid_count=0,
            blank_gid_rows=0,
            unparseable_gid_rows=1,
        ),
        id="gid-in-pseudo-reserved-range",
    ),
    pytest.param(
        OrderedGidCensusShape(
            rows=((StringScalar("not numeric"), SignedIntegerScalar("1"), StringScalar("invalid")),),
            duplicate_extra_rows=0,
            exact_duplicate_extra_rows=0,
            conflicting_extra_rows=0,
            duplicate_details={},
            projection_status="FAILED",
            diagnostic_code=ProjectionDiagnosticCode.ROW_INTEGRITY.value,
            diagnostic_message="ordered integer cell is not numeric",
            real_gid_count=0,
            pseudo_gid_count=0,
            blank_gid_rows=0,
            unparseable_gid_rows=1,
        ),
        id="unparseable-gid-is-counted-separately",
    ),
)


@pytest.mark.parametrize("shape", ORDERED_GID_CENSUS_SHAPES)
@pytest.mark.unit
def test_ordered_gid_census_counts_real_keys_and_projects_one_reader_pass(
    monkeypatch: pytest.MonkeyPatch,
    shape: OrderedGidCensusShape,
) -> None:
    reader_calls = 0

    def iter_rows() -> Iterator[tuple[object, ...]]:
        nonlocal reader_calls
        reader_calls += 1
        if reader_calls > 1:
            raise AssertionError("census must consume each ordered table reader once")
        return iter(shape.rows)

    table = SimpleNamespace(
        descriptor=SimpleNamespace(
            table_name="ordered",
            primary_key_columns=(),
            row_count=len(shape.rows),
            columns=tuple(SimpleNamespace(name=name) for name in ("gid", "no", "payload")),
        ),
        reader=SimpleNamespace(iter_rows=iter_rows),
    )

    def resolve_ordered_rule(
        _ruleset: object,
        _table_name: str,
        *,
        primary_key_columns: tuple[str, ...],
    ) -> SimpleNamespace:
        del primary_key_columns
        return SimpleNamespace(
            record=SimpleNamespace(
                static_role=TableStaticRole.ORDERED_DIFF,
                canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            )
        )

    monkeypatch.setattr(real_dump_census, "resolve_table_rule", resolve_ordered_rule)
    monkeypatch.setattr(
        real_dump_census,
        "derive_storage_rule_view",
        lambda _record, _descriptor: SimpleNamespace(
            canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
            canonical_key_columns=("gid",),
            ordered_policy=OrderedPolicy.GID_NO_V1,
        ),
    )

    result = real_dump_census._duplicate_and_effective_key_stats(
        table_set=SimpleNamespace(tables=(table,)),  # type: ignore[arg-type]
        ruleset=object(),
        diagnostic_mode=True,
        materialization_complete=True,
    )

    assert reader_calls == 1
    assert result.duplicate_by_table == (
        {"ordered": shape.duplicate_extra_rows} if shape.duplicate_extra_rows else {}
    )
    assert result.duplicate_extra_rows == shape.duplicate_extra_rows
    assert result.exact_duplicate_extra_rows == shape.exact_duplicate_extra_rows
    assert result.conflicting_extra_rows == shape.conflicting_extra_rows
    expected_details = {"ordered": shape.duplicate_details} if shape.duplicate_extra_rows else {}
    assert result.duplicate_details_by_table == expected_details
    assert result.ordered_projection_by_table == {
        "ordered": {
            "status": shape.projection_status,
            "diagnostic_code": shape.diagnostic_code,
            "diagnostic_message": shape.diagnostic_message,
            "row_count": len(shape.rows),
            "real_gid_count": shape.real_gid_count,
            "pseudo_gid_count": shape.pseudo_gid_count,
            "blank_gid_rows": shape.blank_gid_rows,
            "unparseable_gid_rows": shape.unparseable_gid_rows,
        }
    }


@pytest.mark.unit
def test_ordered_projection_dataset_summary_matches_table_records() -> None:
    table_details: dict[str, dict[str, Any]] = {
        "complete": {
            "status": "COMPLETE",
            "diagnostic_code": None,
            "real_gid_count": 2,
            "pseudo_gid_count": 1,
        },
        "failed": {
            "status": "FAILED",
            "diagnostic_code": "ROW_INTEGRITY",
            "real_gid_count": 3,
            "pseudo_gid_count": 0,
        },
    }

    report = real_dump_census._ordered_projection_report(table_details, diagnostic_mode=True)

    assert report["ordered_table_count"] == 2
    assert report["complete_count"] == 1
    assert report["failed_count"] == 1
    assert report["failures_by_code"] == {"ROW_INTEGRITY": 1}
    assert report["real_rows_total"] == 5
    assert report["pseudo_rows_total"] == 1
    assert report["tables"] == dict(sorted(table_details.items()))


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
