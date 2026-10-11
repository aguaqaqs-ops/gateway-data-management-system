"""S5 logical records ordering, detail and typed-value contract tests."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from gateway_shared_kernel import (
    BinaryScalar,
    DateScalar,
    DecimalScalar,
    Float64Scalar,
    NullScalar,
    TimestampScalar,
    raw_blob_digest,
)

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison import (
    ComparisonRecord,
    ComparisonRecordKind,
    DetailedFactsResult,
    DatasetReplacementResult,
    PairResultStatus,
    RecordsArtifactFamily,
    compare_plan,
    publish_records_closure,
    read_records_artifact,
)
from tests.test_comparison_artifacts import _standard_result
from tests.test_comparison_standard import _plan as standard_plan
from gateway_backend.capabilities.table_rules.contracts import TableArtifactScope

pytestmark = pytest.mark.unit


def test_records_canonical_sort_is_independent_of_input_order() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'before'), (2, 'deleted');
    """
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'current'), (3, 'added');
    """
    source = compare_plan(standard_plan(before, current))
    assert isinstance(source, DetailedFactsResult)
    assert source.facts is not None
    table = source.facts.tables[0]
    reversed_result = DetailedFactsResult(
        pair_id=source.pair_id,
        status=source.status,
        facts=replace(
            source.facts,
            tables=(replace(table, records=tuple(reversed(table.records))),),
        ),
        diagnostics=source.diagnostics,
    )

    first = publish_records_closure(source, InMemoryArtifactStore())
    second = publish_records_closure(reversed_result, InMemoryArtifactStore())
    assert isinstance(first, DetailedFactsResult)
    assert isinstance(second, DetailedFactsResult)
    assert first.records_closure is not None
    assert second.records_closure is not None
    assert first.records_closure.records[0].records_content_digest == (
        second.records_closure.records[0].records_content_digest
    )


def test_duplicate_logical_records_fail_closed() -> None:
    source = _standard_result()
    assert source.facts is not None
    table = source.facts.tables[0]
    duplicated = DetailedFactsResult(
        pair_id=source.pair_id,
        status=source.status,
        facts=replace(source.facts, tables=(replace(table, records=table.records * 2),)),
    )
    result = publish_records_closure(duplicated, InMemoryArtifactStore())
    assert type(result).__name__ == "FailedResult"
    assert result.facts is None
    assert result.records_closure is None


def test_records_preserve_null_binary_float_decimal_and_temporal_values() -> None:
    source = _standard_result()
    assert source.facts is not None
    table = source.facts.tables[0]
    original = table.records[0]
    typed = ComparisonRecord(
        table_name=original.table_name,
        record_kind=ComparisonRecordKind.ROW_MODIFIED,
        row_identity=original.row_identity,
        changed_columns=("binary", "date", "decimal", "float", "stamp", "nullable"),
        before_values=(
            ("binary", BinaryScalar(b"\x00\xff")),
            ("date", DateScalar("2026-08-20")),
            ("decimal", DecimalScalar("12.340")),
            ("float", Float64Scalar("8000000000000000")),
            ("stamp", TimestampScalar("2026-08-20T00:00:00Z")),
            ("nullable", NullScalar()),
        ),
        current_values=(
            ("binary", BinaryScalar(b"\x01\xfe")),
            ("date", DateScalar("2026-08-21")),
            ("decimal", DecimalScalar("12.350")),
            ("float", Float64Scalar("8008000000000000")),
            ("stamp", TimestampScalar("2026-08-21T00:00:00Z")),
            ("nullable", NullScalar()),
        ),
    )
    facts = replace(source.facts, tables=(replace(table, records=(typed,)),))
    result = DetailedFactsResult(
        pair_id=source.pair_id,
        status=source.status,
        facts=facts,
        diagnostics=source.diagnostics,
    )
    store = InMemoryArtifactStore()
    published = publish_records_closure(result, store)
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    entry = published.records_closure.records[0]
    assert entry.family is RecordsArtifactFamily.STANDARD
    row = read_records_artifact(store, entry)[0]
    before_values = {
        cast(str, item["column_name"]): cast(dict[str, object], item["value"])
        for item in cast(list[dict[str, object]], row["before_values"])
    }
    assert before_values["binary"]["raw_bytes"] == b"\x00\xff"
    assert before_values["float"]["text"] == "8000000000000000"
    assert before_values["date"]["text"] == "2026-08-20"
    assert before_values["decimal"]["text"] == "12.340"
    assert before_values["stamp"]["text"] == "2026-08-20T00:00:00Z"
    assert before_values["nullable"]["kind"] == "null"


def test_update_only_publishes_only_update_records() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'before'), (2, 'deleted');
    """
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'current'), (3, 'added');
    """
    result = compare_plan(standard_plan(before, current, scope=TableArtifactScope.UPDATE_ONLY))
    assert isinstance(result, DetailedFactsResult)
    published = publish_records_closure(result, InMemoryArtifactStore())
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    assert published.records_closure.records[0].record_count == 1


def test_dataset_replacement_rejects_a_records_ref() -> None:
    source = _standard_result()
    assert source.facts is not None
    facts_with_ref = replace(
        source.facts,
        records_ref=ArtifactRef(
            "replacement-closure",
            "application/json",
            0,
            raw_blob_digest(b""),
        ),
    )
    with pytest.raises(ValueError, match="records_ref"):
        DatasetReplacementResult(
            pair_id=source.pair_id,
            status=PairResultStatus.CHANGED,
            facts=facts_with_ref,
        )
