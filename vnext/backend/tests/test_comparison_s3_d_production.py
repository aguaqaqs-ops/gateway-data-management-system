"""D production Arrow route against fixed comparison facts, not native output."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace

import pyarrow as pa
import pytest

from gateway_backend.capabilities.comparison import BoundSnapshotInput, DetailedFactsResult, compare_plan
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.risk_evaluation._facts import RiskRecordView
from gateway_backend.capabilities.snapshot_materialization import snapshot_table_from_arrow
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from tests.support.comparison_s3_c_inputs import bound, canonical_stream, plan

pytestmark = pytest.mark.unit


def _canonical_bound(source: BoundSnapshotInput) -> BoundSnapshotInput:
    assert source.table_set is not None
    tables = []
    for item in source.table_set.tables:
        assert isinstance(item.reader, BoundSnapshotTableReader)
        with closing(canonical_stream(item)) as stream:
            backing = stream.read_all()
        tables.append(snapshot_table_from_arrow(
            item.descriptor, backing, item.reader.source_descriptor(),
            ordered=item.ordered_metadata,
        ))
    return replace(source, table_set=replace(source.table_set, tables=tuple(tables)))


@pytest.mark.parametrize(
    ("before_sql", "current_sql", "record_kinds"),
    (
        (
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'before');",
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, NULL);",
            ("ROW_MODIFIED",),
        ),
        (
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL, obsolete TEXT NULL); "
            "INSERT INTO t VALUES (1, 'before', 'old');",
            "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); "
            "INSERT INTO t VALUES (1, 'after');",
            ("ROW_MODIFIED", "SCHEMA_CHANGE"),
        ),
    ),
)
def test_production_standard_preserves_fixed_facts_and_facts_order_risk_view(
    before_sql: str, current_sql: str, record_kinds: tuple[str, ...],
) -> None:
    before = bound(before_sql)
    current = bound(current_sql)
    old = compare_plan(plan(before, current))
    assert isinstance(old, DetailedFactsResult) and old.facts is not None
    expected = old.facts

    native_plan = plan(_canonical_bound(before), _canonical_bound(current))
    product = compare_plan_native(native_plan)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        actual = product.result.facts
        assert actual is not None
        assert actual.facts_core_digest == expected.facts_core_digest
        assert actual.comparison_digest == expected.comparison_digest
        assert actual.tables[0].table_fact_digest == expected.tables[0].table_fact_digest
        assert actual.tables[0].row_modified_count == 1
        handle = product.handles["t"]
        with closing(handle.risk_record_batches()) as reader:
            assert reader.schema.field("row_identity").type == pa.binary(32)
            assert reader.schema.field("changed_columns").type == pa.list_(pa.string())
        assert tuple(record.record_kind.value for record in RiskRecordView(handle)) == record_kinds
    finally:
        product.close()
