"""Real C Stream business integration and frozen Python-owner differentials."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any, cast

import pyarrow as pa
import pytest
from gateway_compute._native import (
    _canonical_project_native,
    _encode_canonical_ipc_native,
    _parse_sql_native,
    _sql_materialize_native,
)

from gateway_backend.capabilities.snapshot_materialization._catalog import (
    CatalogError,
    extract_special_device_catalog,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    MaterializationStage,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.snapshot_materialization.native import (
    catalog_from_arrow_result,
    filter_arrow_catalog,
    materialize_arrow_table,
)
from gateway_backend.capabilities.storage_projection.native import build_projection_plan, project_arrow_table
from gateway_backend.capabilities.storage_projection.project import project_canonical_table_set
from gateway_backend.capabilities.storage_projection.project import project_storage
from gateway_backend.capabilities.storage_projection.contracts import (
    STORAGE_PROJECTION_VERSION,
    ProjectionInvocationContext,
    ProjectionRequest,
    ProjectionTableInput,
)
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view
from gateway_backend.capabilities.table_access.contracts import RESOURCE_BUDGETS, NeverCancel
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot
from tests.support.snapshot_materialization import load_sql, materialize_sql
from tests.support.storage_projection import table_input, typed_column

_BUDGETS = {
    "max_columns": 2048, "max_batches": 64, "max_rows": 100000,
    "max_metadata_bytes": 4 * 1024 * 1024, "max_input_bytes": 32 * 1024 * 1024,
    "max_live_bytes": 256 * 1024 * 1024, "max_output_bytes": 64 * 1024 * 1024,
    "max_diagnostic_bytes": 512 * 1024,
}
_IPC = {
    "max_columns": 2048, "max_input_batches": 64, "max_rows": 100000,
    "max_descriptor_bytes": 4 * 1024 * 1024, "max_input_bytes": 32 * 1024 * 1024,
    "max_codec_peak_bytes": 256 * 1024 * 1024, "max_output_bytes": 64 * 1024 * 1024,
}


def _tables(sql: str) -> list[dict[str, Any]]:
    result = cast(dict[str, Any], _parse_sql_native(sql.encode(), NeverCancel(), None, 1))
    return cast(list[dict[str, Any]], result["tables"])


def _view(descriptor: SnapshotTableDescriptor) -> Any:
    rules = migrated_table_ruleset_snapshot()
    record = resolve_table_rule(rules, descriptor.table_name, primary_key_columns=descriptor.primary_key_columns).record
    view = derive_storage_rule_view(record, descriptor)
    assert view is not None
    return view


def _projection(sql: str) -> tuple[dict[str, Any], Any]:
    old = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert old.table_set is not None
    descriptor = old.table_set.tables[0].descriptor
    assert descriptor.raw_content_digest is not None
    oracle = project_canonical_table_set(old.table_set, migrated_table_ruleset_snapshot())
    result = project_arrow_table(
        _tables(sql)[0], descriptor, _view(descriptor), canonicalized_input=False,
        cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1,
    )
    return result, oracle


def test_real_parser_sql_projection_ipc_chain_matches_frozen_python_digest() -> None:
    sql = "CREATE TABLE t (id INT UNSIGNED NOT NULL PRIMARY KEY, s SET('b','a'), f FLOAT); INSERT INTO t VALUES (2,'a,b',-0.0),(1,'',1.25);"
    old = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert old.table_set is not None
    descriptor = old.table_set.tables[0].descriptor
    assert descriptor.raw_content_digest is not None
    raw = materialize_arrow_table(
        _tables(sql)[0], effective_compare_key_columns=("id",), stage=MaterializationStage.FINAL,
        cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1,
    )
    assert raw["output"]["raw_content_digest"] == descriptor.raw_content_digest.value
    projected = project_arrow_table(
        raw["output"]["tables"][0], descriptor, _view(descriptor), canonicalized_input=False,
        cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1,
    )
    oracle = project_canonical_table_set(old.table_set, migrated_table_ruleset_snapshot())
    assert oracle.tables[0].descriptor.raw_content_digest is not None
    assert projected["output"]["raw_content_digest"] == oracle.tables[0].descriptor.raw_content_digest.value
    table = projected["output"]["tables"][0]
    ipc = _encode_canonical_ipc_native(table["columns"], table["arrow_stream"], NeverCancel(), _IPC)
    decoded = pa.ipc.open_file(pa.BufferReader(ipc)).read_all()
    assert decoded.column("id").to_pylist() == [1, 2]
    assert decoded.column("s").to_pylist() == ["", "b,a"]
    assert decoded.column("f").to_pylist() == [1.25, 0.0]


_KEY_CASES = (
    ("INT", "NULL", "KEY_NULL"),
    ("VARCHAR(8)", "''", "KEY_EMPTY"),
    ("SET('a')", "''", "UNSUPPORTED_TABLE"),
    ("SET('a')", "NULL", "KEY_NULL"),
    ("TEXT", "'a'", "UNSUPPORTED_TABLE"),
)


@pytest.mark.parametrize(("sql_type", "value", "code"), _KEY_CASES)
def test_native_key_blockers_match_the_existing_projection_owner(sql_type: str, value: str, code: str) -> None:
    result, oracle = _projection(f"CREATE TABLE comm_user_data (data_key {sql_type} NULL); INSERT INTO comm_user_data VALUES ({value});")
    assert result["output"] is None
    assert result["diagnostics"][0]["code"] == code
    assert oracle.diagnostics[0].code.value == code


def test_sql_duplicate_warning_stays_distinct_from_projection_blocker() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1),(1);"
    raw = materialize_arrow_table(_tables(sql)[0], effective_compare_key_columns=("id",), stage=MaterializationStage.PROVISIONAL, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
    assert raw["output"]["raw_content_digest"] is None
    assert raw["output"]["tables"][0]["row_count"] == 2
    assert raw["diagnostics"][0]["code"] == "DUPLICATE_EFFECTIVE_KEY"
    result, oracle = _projection(sql)
    assert result["output"] is None and result["diagnostics"][0]["code"] == "KEY_DUPLICATE"
    assert oracle.diagnostics[0].code.value == "KEY_DUPLICATE"


@pytest.mark.parametrize("gid", ("4_000_000_000", "+４０００００００００", " ٤٠٠٠٠٠٠٠٠٠ "))
def test_reserved_source_gid_strings_follow_the_python_int_owner(gid: str) -> None:
    assert 4_000_000_000 <= int(gid) <= 4_294_967_295
    sql = f"CREATE TABLE t (gid VARCHAR(64)); INSERT INTO t VALUES ('{gid}');"
    raw = materialize_arrow_table(_tables(sql)[0], effective_compare_key_columns=(), stage=MaterializationStage.FINAL, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
    assert raw["output"] is None
    assert raw["diagnostics"][0]["code"] == "RESERVED_PSEUDO_GID"
    assert materialize_sql(sql).snapshot is None


@pytest.mark.parametrize("mismatch", ("type", "nullable"))
def test_empty_stream_checks_actual_schema_and_returns_a_standard_empty_reader(mismatch: str) -> None:
    table = _tables("CREATE TABLE t (id INT NOT NULL PRIMARY KEY);")[0]
    schema = pa.schema([pa.field("id", pa.int64(), nullable=False)])
    result = _sql_materialize_native([{**table, "arrow_stream": pa.RecordBatchReader.from_batches(schema, [])}], {"stage": "FINAL", "effective_compare_key_columns": ["id"]}, NeverCancel(), _BUDGETS)
    output = result["output"]["tables"][0]
    assert output["row_count"] == 0
    assert output["arrow_stream"].read_all().schema == schema
    wrong = pa.schema([pa.field("id", pa.string() if mismatch == "type" else pa.int64(), nullable=mismatch == "nullable")])
    with pytest.raises(ValueError, match="binding"):
        _sql_materialize_native([{**table, "arrow_stream": pa.RecordBatchReader.from_batches(wrong, [])}], {"stage": "FINAL", "effective_compare_key_columns": ["id"]}, NeverCancel(), _BUDGETS)


def test_projection_cannot_disguise_an_empty_source_text_key_as_varchar() -> None:
    sql = "CREATE TABLE t (id TEXT NOT NULL PRIMARY KEY);"
    old = materialize_sql(sql)
    assert old.summary is not None
    descriptor = old.summary.tables[0]
    plan = build_projection_plan(descriptor, _view(descriptor), canonicalized_input=False, budgets=_BUDGETS)
    plan["columns"][0]["sql_type"] = "VARCHAR(8)"
    table = _tables(sql)[0]
    result = _canonical_project_native([table], plan, NeverCancel(), _BUDGETS)
    assert result["output"] is None
    assert any(item["code"] == "UNSUPPORTED_TABLE" for item in result["diagnostics"])


def test_zero_column_nonempty_projection_survives_c_stream_and_canonical_ipc() -> None:
    sql = "CREATE TABLE t (v INT); INSERT INTO t VALUES (1),(1),(2);"
    old = materialize_sql(sql)
    assert old.summary is not None
    descriptor = old.summary.tables[0]
    plan = build_projection_plan(descriptor, _view(descriptor), canonicalized_input=False, budgets=_BUDGETS)
    plan["columns"] = []
    plan["canonical_key_columns"] = []
    plan["structural_columns"] = []
    plan["row_policy"] = "KEYLESS"
    table = _tables(sql)[0]
    result = _canonical_project_native([table], plan, NeverCancel(), _BUDGETS)
    projected = result["output"]["tables"][0]
    assert projected["row_count"] == 3
    encoded = _encode_canonical_ipc_native([], projected["arrow_stream"], NeverCancel(), _IPC)
    decoded = pa.ipc.open_file(pa.BufferReader(encoded)).read_all()
    assert decoded.num_columns == 0 and decoded.num_rows == 3


@pytest.mark.parametrize("gid,no", (("'7'", "1"), ("7", "0"), ("4000000000", "1")))
def test_ordered_native_errors_keep_the_python_owner_classification(gid: str, no: str) -> None:
    # A non-empty numeric string is deliberately not the SQL reserved-gid parser.
    sql_type = "VARCHAR(16)" if gid.startswith("'") else "BIGINT"
    sql = f"CREATE TABLE b1_n1_iec104_syx_list (gid {sql_type}, no INT NOT NULL); INSERT INTO b1_n1_iec104_syx_list VALUES ({gid},{no});"
    if gid == "4000000000":
        # Source materialization correctly rejects this before projection.
        raw = materialize_arrow_table(_tables(sql)[0], effective_compare_key_columns=(), stage=MaterializationStage.FINAL, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
        assert raw["output"] is None and raw["diagnostics"][0]["code"] == "RESERVED_PSEUDO_GID"
        return
    result, oracle = _projection(sql)
    assert result["output"] is None
    assert result["diagnostics"][0]["code"] == oracle.diagnostics[0].code.value == "ROW_INTEGRITY"


def test_canonicalized_ordered_pseudo_gid_requires_the_original_no_allocation() -> None:
    sql = "CREATE TABLE b1_n1_iec104_syx_list (gid BIGINT, no INT NOT NULL); INSERT INTO b1_n1_iec104_syx_list VALUES (0,2),(7,1);"
    old = materialize_sql(sql)
    assert old.summary is not None
    descriptor = old.summary.tables[0]
    plan = build_projection_plan(descriptor, _view(descriptor), canonicalized_input=False, budgets=_BUDGETS)
    source = _tables(sql)[0]
    first = _canonical_project_native([source], plan, NeverCancel(), _BUDGETS)["output"]
    table = first["tables"][0]
    plan["canonicalized_input"] = True
    plan["columns"][0]["source_index"] = 0
    second = _canonical_project_native([table], plan, NeverCancel(), _BUDGETS)
    assert second["output"]["raw_content_digest"] == first["raw_content_digest"]


def test_catalog_filtered_payload_and_source_count_match_the_python_exception() -> None:
    sql = """
        CREATE TABLE device (gid BIGINT, dev_addr INT, description TEXT);
        INSERT INTO device VALUES (1, 1, ''), (2, 65532, '复合信号虚装置');
        CREATE TABLE device_st (gid BIGINT, dev_addr INT, name TEXT, i BIGINT UNSIGNED, f FLOAT, b VARBINARY(8), s SET('b','a'), dt DATETIME);
        INSERT INTO device_st VALUES (3,65532,'point',18446744073709551615,1.25,X'00ff','a,b','2024-01-02 03:04:05'),(NULL,NULL,NULL,1,2.0,X'',NULL,NULL);
    """
    oracle = extract_special_device_catalog(materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED))
    result = filter_arrow_catalog({table["canonical_name"]: table for table in _tables(sql)}, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
    catalog = catalog_from_arrow_result(result, budgets=_BUDGETS, cancel_probe=NeverCancel(), deadline_monotonic=None)
    assert catalog.source_device_row_count == 2
    assert catalog.points == oracle.points
    assert catalog.devices == tuple(device for device in oracle.devices if device.dev_addr == 65532)


@pytest.mark.parametrize("sql", (
    "CREATE TABLE device (gid TEXT, dev_addr INT, description TEXT); INSERT INTO device VALUES ('bad',1,'ordinary');",
    "CREATE TABLE device_st (gid INT, dev_addr TEXT, name TEXT); INSERT INTO device_st VALUES (NULL,'ordinary',NULL);",
))
def test_catalog_cannot_hide_bad_ordinary_identity_rows_by_filtering(sql: str) -> None:
    with pytest.raises(CatalogError):
        extract_special_device_catalog(materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED))
    result = filter_arrow_catalog({table["canonical_name"]: table for table in _tables(sql)}, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
    assert result["output"] is None and result["diagnostics"][0]["code"] == "CATALOG_UNAVAILABLE"


def test_native_stream_budget_stops_before_consuming_later_batches() -> None:
    table = _tables("CREATE TABLE t (id INT);")[0]
    schema = pa.schema([pa.field("id", pa.int64())])
    consumed: list[int] = []

    def batches() -> Iterator[pa.RecordBatch]:
        for index in range(5):
            consumed.append(index)
            yield pa.record_batch([pa.array([index], pa.int64())], schema=schema)

    reader = pa.RecordBatchReader.from_batches(schema, batches())
    with pytest.raises(MemoryError, match="row"):
        _sql_materialize_native([{**table, "arrow_stream": reader}], {"stage": "FINAL", "effective_compare_key_columns": []}, NeverCancel(), {**_BUDGETS, "max_rows": 1})
    assert consumed == [0, 1]


@pytest.mark.parametrize("budget", ("max_metadata_bytes", "max_live_bytes", "max_input_bytes", "max_diagnostic_bytes"))
def test_native_business_resource_failures_return_no_partial_result(budget: str) -> None:
    sql = "CREATE TABLE t (gid VARCHAR(32)); INSERT INTO t VALUES ('4000000000');"
    table = _tables(sql)[0]
    with pytest.raises(MemoryError):
        _sql_materialize_native([table], {"stage": "FINAL", "effective_compare_key_columns": []}, NeverCancel(), {**_BUDGETS, budget: 1})


def test_complete_schema_diagnostics_keep_the_existing_cap_order_and_omitted_count() -> None:
    # The existing projection owner permits a bound metadata descriptor wider
    # than the SQL parser default. Raise only this test's explicit parser bound.
    names = tuple(f"c{index:04d}" for index in range(1050))
    sql = "CREATE TABLE t (" + ",".join(f"{name} JSON" for name in names) + ");"
    raw = cast(dict[str, Any], _parse_sql_native(sql.encode(), NeverCancel(), None, 1, replace(RESOURCE_BUDGETS, max_columns_per_table=2000)))
    assert raw["status"] == "COMPLETE", raw["diagnostics"]
    table = raw["tables"][0]
    reader, binding = table_input("t", columns=tuple(typed_column(name, "JSON", nullable=True) for name in names), primary_key_columns=(), row_count=0)
    oracle = project_storage(ProjectionRequest(ruleset=migrated_table_ruleset_snapshot(), storage_projection_version=STORAGE_PROJECTION_VERSION, tables=(ProjectionTableInput(canonical_table="t", reader=reader, source_binding=binding),), context=ProjectionInvocationContext(NeverCancel())))
    budgets = {**_BUDGETS, "max_metadata_bytes": 32 * 1024 * 1024, "max_live_bytes": 512 * 1024 * 1024}
    plan = build_projection_plan(binding.descriptor, _view(binding.descriptor), canonicalized_input=False, budgets=budgets)
    result = _canonical_project_native([table], plan, NeverCancel(), budgets)
    assert result["output"] is None
    assert [(item["code"], item["column"]) for item in result["diagnostics"]] == [(item.code.value, item.column_name) for item in oracle.diagnostics]
    assert len(result["diagnostics"]) == 1024
    assert result["omitted_diagnostic_count"] == oracle.omitted_diagnostic_count == 26


def test_dropped_unsupported_columns_stay_out_of_canonical_digest() -> None:
    digests = []
    for value in ("'{\"a\":1}'", "'{\"a\":2}'"):
        # net_cfg's no column is dropped by its real rule, independent of type.
        sql = f"CREATE TABLE net_cfg (board VARCHAR(8) NOT NULL, link_no INT NOT NULL, no JSON); INSERT INTO net_cfg VALUES ('eth0',1,{value});"
        result, oracle = _projection(sql)
        assert result["output"] is not None
        assert oracle.tables[0].descriptor.raw_content_digest is not None
        assert result["output"]["raw_content_digest"] == oracle.tables[0].descriptor.raw_content_digest.value
        digests.append(result["output"]["raw_content_digest"])
    assert digests[0] == digests[1]


@pytest.mark.parametrize(("fixture", "status"), (
    ("sql/partial/s2-unknown-type-mixed", "PARTIAL"),
    ("sql/malformed/s2-document-failed", "FAILED"),
))
def test_real_parser_and_per_table_facts_keep_existing_snapshot_status_ownership(fixture: str, status: str) -> None:
    sql = load_sql(f"{fixture}/input.sql")
    parsed = cast(dict[str, Any], _parse_sql_native(sql.encode(), NeverCancel(), None, 1))
    oracle = materialize_sql(sql)
    assert parsed["status"] == oracle.status.value == status
    if status == "FAILED":
        assert oracle.snapshot is None and oracle.table_set is None
        assert all(not table["reader_ready"] for table in parsed["tables"])
        return
    assert oracle.summary is not None
    for table in parsed["tables"]:
        descriptor = next(item for item in oracle.summary.tables if item.table_name == table["canonical_name"])
        if not table["reader_ready"]:
            assert table["arrow_stream"] is None and descriptor.raw_content_digest is None
            continue
        result = materialize_arrow_table(table, effective_compare_key_columns=descriptor.compare_key_columns, stage=MaterializationStage.FINAL, cancel_probe=NeverCancel(), budgets=_BUDGETS, deadline_monotonic=None, pool_threads=1)
        assert descriptor.raw_content_digest is not None
        assert result["output"]["raw_content_digest"] == descriptor.raw_content_digest.value


@pytest.mark.serial
@pytest.mark.parametrize("mode", ("cancel", "deadline", "probe_error"))
def test_native_business_control_is_observed_while_the_gil_is_released(mode: str) -> None:
    class Probe:
        count = 0

        def is_set(self) -> bool:
            self.count += 1
            if self.count > 1 and mode == "probe_error":
                raise RuntimeError("broken probe")
            return self.count > 1 and mode == "cancel"

    table = _tables("CREATE TABLE t (id INT);")[0]
    schema = pa.schema([pa.field("id", pa.int64())])
    reader = pa.RecordBatchReader.from_batches(schema, [pa.record_batch([pa.array(range(50000), pa.int64())], schema=schema)])
    probe = Probe()
    expected = {"cancel": InterruptedError, "deadline": TimeoutError, "probe_error": RuntimeError}[mode]
    deadline = time.monotonic() + 0.02 if mode == "deadline" else None
    with pytest.raises(expected):
        _sql_materialize_native([{**table, "arrow_stream": reader}], {"stage": "FINAL", "effective_compare_key_columns": []}, probe, _BUDGETS, deadline)
    if mode != "deadline":
        assert probe.count > 1
