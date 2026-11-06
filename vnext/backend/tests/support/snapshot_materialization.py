"""Helpers for SQL Snapshot materialization tests. Not a production materializer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_backend.capabilities.composite_signal.contracts import (
    CompositeLogicSource,
    empty_composite_logic_source,
    present_composite_logic_source,
)
from gateway_backend.capabilities.snapshot_materialization.compose import (
    materialize_business_snapshot,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BusinessSnapshotMaterializationRequest,
    MaterializationPolicy,
    MaterializationStage,
    SnapshotMaterializationResult,
    SqlSnapshotMaterializationRequest, SnapshotTable,
)
from gateway_backend.capabilities.snapshot_materialization.materialize import (
    materialize_sql_snapshot,
)
from gateway_backend.capabilities.table_access.contracts import (
    NeverCancel,
    ParseResult,
    ParserInvocationContext,
    XmlParseResult,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableRulesetSnapshot,
)
from gateway_shared_kernel import DigestRef, raw_blob_digest
from tests.support.table_access_sql import sql_request
from tests.support.table_access_xml import parse_xml_text

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "snapshot-materialization"
)
_ZERO = DigestRef("sha256:" + "00" * 32)


def load_sql(relative_path: str) -> str:
    return (FIXTURE_ROOT / relative_path).read_text(encoding="utf-8")


def load_expected(relative_path: str) -> dict[str, Any]:
    payload = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("expected.json must be an object")
    return payload


def parse_fixture(relative_path: str, context: ParserInvocationContext | None = None) -> ParseResult:
    return parse_sql(sql_request(load_sql(relative_path), context))


def default_ruleset() -> TableRulesetSnapshot:
    return TableRulesetSnapshot(table_ruleset_version=TABLE_RULESET_VERSION)


def materialize_sql(
    sql: str | bytes | ParseResult,
    *,
    stage: MaterializationStage = MaterializationStage.FINAL,
    policy: MaterializationPolicy = MaterializationPolicy.DESCRIPTOR_ONLY,
    ruleset: TableRulesetSnapshot | None = None,
    requested_tables: tuple[str, ...] | None = None,
    context: ParserInvocationContext | None = None,
    sql_source_digest: DigestRef | None = None,
    artifact_store: object | None = None,
) -> SnapshotMaterializationResult:
    if isinstance(sql, ParseResult):
        parse_result = sql
        digest = sql_source_digest or _ZERO
    else:
        request = sql_request(sql, context)
        parse_result = parse_sql(request)
        digest = sql_source_digest or raw_blob_digest(request.sql_utf8)
    return materialize_sql_snapshot(
        SqlSnapshotMaterializationRequest(
            parse_result=parse_result,
            sql_source_digest=digest,
            ruleset=ruleset or default_ruleset(),
            table_ruleset_version=(ruleset or default_ruleset()).table_ruleset_version,
            materialization_stage=stage,
            policy=policy,
            context=context or ParserInvocationContext(NeverCancel()),
            requested_tables=requested_tables,
            artifact_store=artifact_store,
        )
    )


def summary_payload(result: SnapshotMaterializationResult) -> dict[str, Any]:
    if result.snapshot is None or result.summary is None:
        return {
            "status": result.status.value,
            "diagnostics": [item.code.value for item in result.diagnostics],
        }
    tables = []
    for table in result.summary.tables:
        tables.append(
            {
                "table_name": table.table_name,
                "display_table_name": table.display_table_name,
                "row_count": table.row_count,
                "primary_key_columns": list(table.primary_key_columns),
                "compare_key_columns": list(table.compare_key_columns),
                "degraded_reason": None
                if table.degraded_reason is None
                else table.degraded_reason.value,
                "compare_schema_digest": table.compare_schema_digest.value,
                "business_schema_digest": table.business_schema_digest.value,
                "raw_content_digest": None
                if table.raw_content_digest is None
                else table.raw_content_digest.value,
            }
        )
    return {
        "status": result.status.value,
        "materialization_stage": result.materialization_stage.value,
        "cache_trust_level": result.cache_trust_level.value,
        "table_count": result.summary.table_count,
        "row_count_total": result.summary.row_count_total,
        "snapshot_digest": result.snapshot.snapshot_digest.value,
        "raw_state_digest": result.snapshot.raw_state_digest.value,
        "canonical_state_digest": (
            None
            if result.summary.canonical_state_digest is None
            else result.summary.canonical_state_digest.value
        ),
        "tables": tables,
    }


def materialize_business(
    sql: str | bytes | ParseResult,
    xml: str | bytes | XmlParseResult | None = None,
    *,
    empty: bool = False,
    stage: MaterializationStage = MaterializationStage.FINAL,
    policy: MaterializationPolicy = MaterializationPolicy.DESCRIPTOR_ONLY,
    ruleset: TableRulesetSnapshot | None = None,
    requested_tables: tuple[str, ...] | None = None,
    context: ParserInvocationContext | None = None,
    sql_source_digest: DigestRef | None = None,
    logic: CompositeLogicSource | None = None,
    artifact_store: object | None = None,
) -> SnapshotMaterializationResult:
    sql_result_request = _build_sql_materialization_request(
        sql,
        stage=stage,
        policy=policy,
        ruleset=ruleset,
        requested_tables=requested_tables,
        context=context,
        sql_source_digest=sql_source_digest,
        artifact_store=artifact_store,
    )
    document: XmlParseResult | None
    if empty or xml is None:
        source = logic or empty_composite_logic_source()
        document = None
    elif isinstance(xml, XmlParseResult):
        source = logic or present_composite_logic_source(b"<Logic_Set></Logic_Set>")
        document = xml
    else:
        data = xml.encode("utf-8") if isinstance(xml, str) else xml
        source = logic or present_composite_logic_source(data)
        document = parse_xml_text(data)
    return materialize_business_snapshot(
        BusinessSnapshotMaterializationRequest(
            sql=sql_result_request,
            logic=source,
            xml=document,
        )
    )


def _build_sql_materialization_request(
    sql: str | bytes | ParseResult,
    *,
    stage: MaterializationStage,
    policy: MaterializationPolicy,
    ruleset: TableRulesetSnapshot | None,
    requested_tables: tuple[str, ...] | None,
    context: ParserInvocationContext | None,
    sql_source_digest: DigestRef | None,
    artifact_store: object | None = None,
) -> SqlSnapshotMaterializationRequest:
    resolved = ruleset or default_ruleset()
    if isinstance(sql, ParseResult):
        parse_result = sql
        digest = sql_source_digest or _ZERO
    else:
        request = sql_request(sql)
        parse_result = parse_sql(request)
        digest = sql_source_digest or raw_blob_digest(request.sql_utf8)
    return SqlSnapshotMaterializationRequest(
        parse_result=parse_result,
        sql_source_digest=digest,
        ruleset=resolved,
        table_ruleset_version=resolved.table_ruleset_version,
        materialization_stage=stage,
        policy=policy,
        context=context or ParserInvocationContext(NeverCancel()),
        requested_tables=requested_tables,
        artifact_store=artifact_store,
    )


def materialize_arrow_sql(sql: str | bytes, **kwargs: Any) -> SnapshotMaterializationResult:
    """Target production parser/materializer fixture, independent of the old oracle."""
    from gateway_backend.capabilities.table_access import parse_arrow_sql
    request = sql_request(sql, kwargs.get("context"))
    kwargs.setdefault("sql_source_digest", raw_blob_digest(request.sql_utf8))
    return materialize_sql(parse_arrow_sql(request), **kwargs)


def snapshot_table_as_arrow(table: SnapshotTable) -> SnapshotTable:
    """D/E small reference fixtures cross once into the real Arrow producer path."""
    import struct
    import pyarrow as pa
    from dataclasses import replace
    from gateway_backend.capabilities.snapshot_materialization import (
        ArrowSnapshotTableReader, canonical_columns, snapshot_table_from_arrow, source_descriptor_from_arrow,
    )
    from gateway_backend.capabilities.snapshot_materialization._parquet import _cell_to_arrow
    if table.reader is None:
        raise ValueError("fixture table requires a reader")
    if isinstance(table.reader, ArrowSnapshotTableReader):
        return replace(table, reader=table.reader.reopen(),
            batch_reader=None if table.batch_reader is None else table.batch_reader.reopen())
    descriptor = table.descriptor
    source = source_descriptor_from_arrow({"canonical_name": descriptor.table_name,
        "display_name": descriptor.display_table_name, "columns": canonical_columns(descriptor),
        "primary_key": list(descriptor.primary_key_columns), "reader_ready": True})
    reader = table.reader.reopen()
    try:
        rows = tuple(reader.iter_rows())
    finally:
        reader.close()
    fields = []
    arrays = []
    for index, column in enumerate(source.columns):
        kind = None if column.declared_type is None else column.declared_type.kind.value
        physical = pa.int64() if kind == "signed-integer" else pa.uint64() if kind == "unsigned-integer" else pa.float32() if kind == "float32" else pa.float64() if kind == "float64" else pa.bool_() if kind == "boolean" else pa.binary() if kind in ("binary", "bit") else pa.string()
        values: list[Any] = [_cell_to_arrow(row[index], column) for row in rows]
        if column.logical_type.value == "set":
            values = [None if value is None else ",".join(value) for value in values]
        elif kind in ("signed-integer", "unsigned-integer"):
            values = [None if value is None else int(value) for value in values]
        elif kind in ("float32", "float64"):
            values = [None if value is None else struct.unpack(">f" if kind == "float32" else ">d", bytes.fromhex(value))[0] for value in values]
        fields.append(pa.field(column.canonical_name, physical, nullable=True))
        arrays.append(pa.array(values, type=physical))
    return snapshot_table_from_arrow(descriptor, pa.Table.from_arrays(arrays, schema=pa.schema(fields)), source,
                                     ordered=table.ordered_metadata)
