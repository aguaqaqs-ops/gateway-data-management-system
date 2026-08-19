"""SQL Snapshot status, policy, filter, cancel, and reader lifecycle tests."""

from __future__ import annotations

import time

import pytest
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserDiagnosticCode,
    ParserInvocationContext,
    TableAccessError,
)
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableCompareKey,
    TableRulesetSnapshot,
)
from tests.support.snapshot_materialization import materialize_sql, parse_fixture

POLICY_FAILURES = (
    (
        MaterializationPolicy.ARTIFACTS_REQUIRED,
        MaterializationDiagnosticCode.ARTIFACT_STORE_REQUIRED,
    ),
)


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def test_unknown_type_mixed_is_partial() -> None:
    result = materialize_sql(parse_fixture("sql/partial/s2-unknown-type-mixed/input.sql"))
    assert result.status is SnapshotMaterializationStatus.PARTIAL
    assert result.snapshot is not None
    assert result.summary is not None
    names = {table.table_name: table for table in result.summary.tables}
    assert names["ok"].raw_content_digest is not None
    assert names["bad"].raw_content_digest is None
    assert names["bad"].degraded_reason is not None


def test_all_tables_failed_upgrades_to_failed() -> None:
    sql = "CREATE TABLE bad (id YEAR NOT NULL); INSERT INTO bad VALUES (2020);"
    result = materialize_sql(sql)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.table_set is None


def test_requested_tables_filter_does_not_rediscover() -> None:
    result = materialize_sql(
        parse_fixture("sql/partial/s2-unknown-type-mixed/input.sql"),
        requested_tables=("ok",),
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    assert tuple(table.table_name for table in result.summary.tables) == ("ok",)


def test_missing_requested_table_fails_closed() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        requested_tables=("missing",),
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.REQUESTED_TABLE_MISSING


def test_unknown_compare_key_column_fails_the_table() -> None:
    sql = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    )
    ruleset = TableRulesetSnapshot(
        table_ruleset_version=TABLE_RULESET_VERSION,
        compare_keys=(TableCompareKey(canonical_table="t", key_columns=("nope",)),),
    )
    result = materialize_sql(sql, ruleset=ruleset)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.COMPARE_KEY_UNKNOWN_COLUMN


def test_ruleset_version_mismatch_fails_closed() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        ruleset=TableRulesetSnapshot(table_ruleset_version=2),
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.RULESET_VERSION_MISMATCH


@pytest.mark.parametrize(("policy", "code"), POLICY_FAILURES)
def test_policy_failures_are_parameterized(
    policy: MaterializationPolicy, code: MaterializationDiagnosticCode
) -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=policy,
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is code


def test_descriptor_only_omits_table_set() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.DESCRIPTOR_ONLY,
    )
    assert result.table_set is None
    assert result.summary is not None
    assert result.summary.tables[0].row_count == 1


def test_summary_is_usable_without_opening_rows() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.summary is not None
    assert result.table_set is not None
    reader = result.table_set.tables[0].reader
    assert reader is not None
    assert result.summary.tables[0].raw_content_digest is not None
    reader.close()


def test_reader_reopen_close_and_commit() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.table_set is not None
    reader = result.table_set.tables[0].reader
    assert reader is not None
    rows = tuple(reader.iter_rows())
    assert len(rows) == 1
    with pytest.raises(ValueError, match="single-consumer"):
        tuple(reader.iter_rows())
    reopened = reader.reopen()
    reader.close()
    with pytest.raises(TableAccessError) as closed:
        reader.descriptor()
    assert closed.value.code is ParserDiagnosticCode.READER_CLOSED
    assert len(tuple(reopened.iter_rows())) == 1
    counts = reopened.count_column_values("id")
    assert counts.total_row_count == 1
    reopened.close()
    reopened.close()


def test_cancel_does_not_publish_snapshot() -> None:
    parsed = parse_fixture("sql/valid/s2-minimal-create-insert/input.sql")
    result = materialize_sql(parsed, context=ParserInvocationContext(CountCancel(1)))
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED


def test_timeout_does_not_publish_snapshot() -> None:
    parsed = parse_fixture("sql/valid/s2-minimal-create-insert/input.sql")
    result = materialize_sql(
        parsed,
        context=ParserInvocationContext(
            CountCancel(10_000),
            deadline_monotonic=time.monotonic() - 1.0,
        ),
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.MATERIALIZATION_TIMEOUT
