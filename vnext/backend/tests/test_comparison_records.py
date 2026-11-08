"""Live native records ordering, detail, and typed-value contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison import (
    DatasetReplacementResult, DetailedFactsResult, PairResultStatus,
)
from gateway_backend.capabilities.table_rules.contracts import TableArtifactScope
from tests.support.comparison_s3_e_live import native_product, publish_product
from tests.support.records_diagnostic import standalone_records_batches

pytestmark = pytest.mark.unit


def _record_rows(
    before_sql: str,
    current_sql: str,
    *,
    scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES,
) -> tuple[tuple[dict[str, object], ...], str]:
    product = native_product(before_sql, current_sql, artifact_scope=scope)
    store = InMemoryArtifactStore()
    try:
        published = publish_product(product, store)
        assert published.records_closure is not None
        entry, = published.records_closure.records
        rows = tuple(
            cast(dict[str, object], row)
            for batch in standalone_records_batches(store, entry)
            for row in batch.to_pylist()
        )
        return rows, entry.records_content_digest.value
    finally:
        product.close()


def test_records_sort_is_independent_of_source_row_order() -> None:
    schema = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
    before = schema + " INSERT INTO t VALUES (1,'before'),(2,'deleted');"
    current = schema + " INSERT INTO t VALUES (1,'current'),(3,'added');"
    before_reordered = schema + " INSERT INTO t VALUES (2,'deleted'),(1,'before');"
    current_reordered = schema + " INSERT INTO t VALUES (3,'added'),(1,'current');"
    rows, digest = _record_rows(before, current)
    reordered_rows, reordered_digest = _record_rows(before_reordered, current_reordered)
    assert digest == reordered_digest
    assert rows == reordered_rows
    assert tuple(row["record_kind"] for row in rows) == (
        "ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED",
    )


def test_records_preserve_binary_float_decimal_time_and_null() -> None:
    schema = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, b VARBINARY(8),"
        " f DOUBLE, amount DECIMAL(10,3), dt DATETIME, nullable VARCHAR(8));"
    )
    before = schema + (
        " INSERT INTO t VALUES (1,X'00ff',-0.0,12.340,"
        "'2026-08-20 00:00:00',NULL);"
    )
    current = schema + (
        " INSERT INTO t VALUES (1,X'01fe',1.5,12.350,"
        "'2026-08-21 00:00:00',NULL);"
    )
    rows, _ = _record_rows(before, current)
    row, = rows
    assert row["record_kind"] == "ROW_MODIFIED"
    values = {
        cast(str, item["column_name"]): cast(dict[str, object], item["value"])
        for item in cast(list[dict[str, object]], row["before_values"])
    }
    assert values["b"]["raw_bytes"] == b"\x00\xff"
    assert values["f"]["kind"] == "float64"
    assert values["amount"]["kind"] == "decimal"
    assert values["dt"]["kind"] == "datetime"
    assert values["nullable"]["kind"] == "null"


def test_update_only_publishes_only_update_records() -> None:
    schema = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
    before = schema + " INSERT INTO t VALUES (1,'before'),(2,'deleted');"
    current = schema + " INSERT INTO t VALUES (1,'current'),(3,'added');"
    rows, _ = _record_rows(before, current, scope=TableArtifactScope.UPDATE_ONLY)
    assert tuple(row["record_kind"] for row in rows) == ("ROW_MODIFIED",)


def test_dataset_replacement_rejects_a_records_ref() -> None:
    schema = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
    product = native_product(
        schema + " INSERT INTO t VALUES (1,'before');",
        schema + " INSERT INTO t VALUES (1,'current');",
    )
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        facts_with_ref = replace(
            product.result.facts,
            records_ref=ArtifactRef(
                "replacement-closure", "application/json", 0, raw_blob_digest(b""),
            ),
        )
        with pytest.raises(ValueError, match="records_ref"):
            DatasetReplacementResult(
                pair_id=product.result.pair_id,
                status=PairResultStatus.CHANGED,
                facts=facts_with_ref,
            )
    finally:
        product.close()
