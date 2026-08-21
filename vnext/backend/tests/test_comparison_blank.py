"""S4 blank-row interval semantics."""

from __future__ import annotations

import pytest

from gateway_backend.capabilities.comparison import (
    BlankRecordKind,
    ComparisonFacts,
    ComparisonPlan,
    DetailedFactsResult,
    OrderedRecordKind,
    compare_plan,
)
from tests.test_comparison_ordered import _plan, _table

pytestmark = pytest.mark.unit


def _facts(plan: ComparisonPlan) -> ComparisonFacts:
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    return result.facts


def _before() -> str:
    return """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (NULL, 3, 'y'), (2, 100, 'b');
    """


def test_blank_payload_change_has_no_ordinary_or_blank_record() -> None:
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'changed'), (NULL, 3, 'other'), (2, 100, 'b');
    """

    table = _table(_facts(_plan(_before(), current)))
    assert table.status.value == "UNCHANGED"
    assert table.records == ()
    assert table.blank_extension is not None
    assert table.blank_extension.records == ()

    baseline = _table(_facts(_plan(_before(), _before())))
    assert baseline.table_fact_digest == table.table_fact_digest


def test_blank_occupancy_change_is_an_interval_delete_without_move() -> None:
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'changed'), (2, 4, 'b');
    """

    table = _table(_facts(_plan(_before(), current)))
    assert table.row_added_count == 0
    assert table.row_deleted_count == 0
    assert table.records == ()
    assert table.ordered_extension is not None
    assert not any(
        record.record_kind is OrderedRecordKind.ROW_MOVED
        for record in table.ordered_extension.records
    )
    assert table.blank_extension is not None
    assert [record.record_kind for record in table.blank_extension.records] == [
        BlankRecordKind.DELETE_INTERVAL
    ]
    assert table.blank_extension.blank_summary.interval_deleted_count == 1


def test_blank_occupancy_change_is_an_interval_insert_without_move() -> None:
    current = _before()
    before = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 4, 'b');
    """

    table = _table(_facts(_plan(before, current)))
    assert table.records == ()
    assert table.blank_extension is not None
    assert [record.record_kind for record in table.blank_extension.records] == [
        BlankRecordKind.INSERT_INTERVAL
    ]
    assert table.blank_extension.blank_summary.interval_inserted_count == 1


def test_blank_no_renumber_keeps_occupancy_digest_and_records_stable() -> None:
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 20, 'x'), (NULL, 30, 'y'), (2, 100, 'b');
    """

    table = _table(_facts(_plan(_before(), current)))
    assert table.records == ()
    assert table.ordered_extension is not None
    assert table.ordered_extension.records == ()
    assert table.blank_extension is not None
    assert table.blank_extension.records == ()
    assert (
        table.blank_extension.before_occupancy_digest
        == table.blank_extension.current_occupancy_digest
    )


def test_blank_interval_shift_is_delete_and_insert_without_move_pairing() -> None:
    before = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 3, 'b');
    """
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (2, 2, 'b'), (NULL, 3, 'x');
    """

    table = _table(_facts(_plan(before, current)))
    assert table.records == ()
    assert table.blank_extension is not None
    assert {record.record_kind for record in table.blank_extension.records} == {
        BlankRecordKind.DELETE_INTERVAL,
        BlankRecordKind.INSERT_INTERVAL,
    }
