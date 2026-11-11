"""Pure navigation Contract coverage; no repository or process fixtures."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from contextlib import nullcontext
from dataclasses import replace
from typing import Any

import pytest

from gateway_backend.capabilities.business_navigation import (
    FilterRecord, NavigationEvidence, NavigationRow, NavigationSide, NavigationTable,
    build_navigation, validate_navigation,
)
from gateway_backend.capabilities.business_navigation.contracts import (
    Scalar, validate_diagnostics,
)
from gateway_backend.capabilities.business_navigation.producer import POINT_TABLES, scalar_reason
from gateway_backend.capabilities.risk_evaluation.contracts import RiskLevel

pytestmark = pytest.mark.unit


def side(rows: tuple[Mapping[str, Scalar], ...] = (), *, column: str = "dev_addr",
         sql_type: str = "INT", columns: Mapping[str, str | None] | None = None,
         label: str = "表") -> NavigationSide:
    # Tests deliberately control canonical representative bytes independently of row order.
    data = tuple(NavigationRow(r, str(sorted(r.items())).encode()) for r in rows)
    return NavigationSide(columns or {column: sql_type}, lambda: iter(data), len(data), label)


def evidence(**changes: Any) -> NavigationEvidence:
    return replace(NavigationEvidence(comparison_succeeded=True, risk_attribution_complete=True), **changes)


def table(name: str, old: NavigationSide | None, new: NavigationSide | None, **changes: Any) -> NavigationTable:
    return NavigationTable(name, name, old, new, evidence(), **changes)


def device(old: tuple[Mapping[str, Scalar], ...], new: tuple[Mapping[str, Scalar], ...]) -> NavigationTable:
    columns = {"dev_addr": "INT", "gid": "INT"}
    return table("device", side(old, columns=columns), side(new, columns=columns))


def build(*tables: NavigationTable, replacement: bool = False) -> Any:
    return build_navigation(tables, replacement=replacement, check=lambda: None, reserve=lambda _: nullcontext())


def tabs(result: Any, table_id: str, *, replacement_side: str | None = None) -> list[dict[str, Any]]:
    groups = result.document["groups"] if replacement_side is None else result.document["replacement_sides"][replacement_side]
    return [tab for group in groups for item in group["items"] for tab in item["tabs"] if tab["table_id"] == table_id]


def diagnostics(result: Any, code: str) -> list[dict[str, Any]]:
    return [] if result.diagnostics is None else [d for d in result.diagnostics["diagnostics"] if d["code"] == code]


@pytest.mark.parametrize("name,label", POINT_TABLES)
def test_registry_shared_tables_use_same_side_identity_sets(name: str, label: str) -> None:
    old = ({"dev_addr": 49, "gid": 7}, {"dev_addr": 49, "gid": 8})
    new = ({"dev_addr": 49, "gid": 9},)
    column = "gid" if name == "device_cfg" else "dev_addr"
    source = side(({column: 7 if column == "gid" else 49},), column=column)
    target = side(({column: 9 if column == "gid" else 49},), column=column)
    result = build(device(old, new), table(name, source, target))
    tab = tabs(result, name)[0]
    assert tab["label"] == label
    assert tab["row_filter"]["before"]["values"] == ([7, 8] if column == "gid" else [49])
    assert tab["row_filter"]["current"]["values"] == ([9] if column == "gid" else [49])
    assert tab["facts"]["before_row_count"] == tab["facts"]["current_row_count"] == 1
    assert len(diagnostics(result, "DEVICE_ADDRESS_DUPLICATE")) == 1


@pytest.mark.parametrize("column,old_value,new_value", [("gid", 7, 8), ("dev_addr", 49, 50)])
def test_unmodified_rows_retain_before_filter_identity(column: str, old_value: int, new_value: int) -> None:
    name = "device_cfg" if column == "gid" else "device_st"
    old = {"dev_addr": 49, "gid": 7}
    new = {"dev_addr": new_value if column == "dev_addr" else 49, "gid": new_value if column == "gid" else 7}
    source = side(({column: old_value},), column=column)
    result = build(device((old,), (new,)), table(name, source, source, unchanged=True))
    assert any(t["row_filter"]["before"] and t["row_filter"]["before"]["values"] == [old_value] for t in tabs(result, name))
    orphan = diagnostics(result, "DEVICE_ROWS_UNASSIGNED")
    assert len(orphan) == 1 and orphan[0]["side"] == "CURRENT"
    assert orphan[0]["params"]["row_count"] == 1
    assert orphan[0]["params"]["changed_row_count"] == 0
    assert table(name, source, source, unchanged=True).may_reuse_unrecorded_identity


FALLBACK_CASES = (
    ({"comparison_succeeded": False}, "RECORDS_UNAVAILABLE"),
    ({"expected_record_counts": (1, 0, 0)}, "RECORDS_UNAVAILABLE"),
    ({"suppressed_added_count": 1}, "RECORDS_UNAVAILABLE"),
    ({"suppressed_deleted_count": 1}, "RECORDS_UNAVAILABLE"),
    ({"risk_attribution_complete": False}, "RISK_ATTRIBUTION_UNAVAILABLE"),
    ({"schema_only": True}, "TABLE_DEGRADED"),
    ({"degraded": True}, "TABLE_DEGRADED"),
)


@pytest.mark.parametrize("changes,reason", FALLBACK_CASES)
def test_incomplete_records_or_risk_never_report_exact(changes: dict[str, Any], reason: str) -> None:
    source = side(({"dev_addr": 49},))
    shared = replace(table("device_st", source, source), evidence=evidence(**changes))
    result = build(device(({"dev_addr": 49, "gid": 7},), ({"dev_addr": 49, "gid": 8},)), shared)
    facts = tabs(result, "device_st")[0]["facts"]
    assert facts["basis"] == "TABLE_FALLBACK"
    assert facts["change_kind"] is facts["risk_level"] is None
    assert facts["before_row_count"] == 1
    assert diagnostics(result, "DEVICE_TAB_FACTS_UNAVAILABLE")[0]["params"]["reason"] == reason
    assert not shared.may_reuse_unrecorded_identity


def test_record_context_is_required_even_for_unchanged_identity_column() -> None:
    source = side(({"dev_addr": 49},))
    record = FilterRecord("id", "ROW_MODIFIED", {}, {})
    shared = replace(table("device_st", source, source), evidence=evidence(records=(record,), expected_record_counts=(0, 0, 1), locator_complete=True))
    result = build(device(({"dev_addr": 49, "gid": 1},), ({"dev_addr": 49, "gid": 1},)), shared)
    assert diagnostics(result, "DEVICE_TAB_FACTS_UNAVAILABLE")[0]["params"]["reason"] == "RECORDS_UNAVAILABLE"


def test_table_scope_does_not_paint_local_rows_and_is_identical_across_tabs() -> None:
    source = side(({"dev_addr": 49}, {"dev_addr": 50}))
    shared = replace(table("device_st", source, source, table_change=True), evidence=evidence(table_risk=RiskLevel.HIGH))
    devs = ({"dev_addr": 49, "gid": 7}, {"dev_addr": 50, "gid": 8})
    result = build(device(devs, devs), shared)
    for tab in tabs(result, "device_st"):
        assert tab["facts"]["change_kind"] == "UNCHANGED"
        assert tab["facts"]["risk_level"] is None
        assert tab["facts"]["table_scope"] == {"change": True, "risk_level": "HIGH"}


def test_row_changes_and_risk_attribute_both_sides_once_per_tab() -> None:
    old, new = side(({"dev_addr": 49},)), side(({"dev_addr": 50},))
    record = FilterRecord("id", "ROW_MODIFIED", {"dev_addr": 49}, {"dev_addr": 50}, RiskLevel.HIGH)
    shared = replace(table("device_st", old, new), evidence=evidence(records=(record,), expected_record_counts=(0, 0, 1), locator_complete=True))
    devs = ({"dev_addr": 49, "gid": 7}, {"dev_addr": 50, "gid": 8})
    result = build(device(devs, devs), shared)
    assert [t["facts"]["change_kind"] for t in tabs(result, "device_st")] == ["DELETED", "ADDED"]
    assert all(t["facts"]["risk_level"] == "HIGH" and t["facts"]["table_scope"] is None for t in tabs(result, "device_st"))


@pytest.mark.parametrize("sql_type,value,reason", [
    ("BIGINT", 9007199254740992, "INTEGER_OUT_OF_RANGE"),
    ("DECIMAL(10,0)", "49", "UNSUPPORTED_TYPE"),
    ("BOOLEAN", 1, "UNSUPPORTED_TYPE"),
    ("DOUBLE", 49, "UNSUPPORTED_TYPE"),
])
def test_unsupported_identity_downgrades_whole_table_per_affected_side(sql_type: str, value: Scalar, reason: str) -> None:
    shared = table("device_st", side(({"dev_addr": value},), sql_type=sql_type), side(({"dev_addr": 49},)))
    devs = ({"dev_addr": 49, "gid": 7},)
    result = build(device(devs, devs), shared)
    assert len(tabs(result, "device_st")) == 1
    assert tabs(result, "device_st")[0]["row_filter"] is None
    diag = diagnostics(result, "DEVICE_FILTER_VALUE_UNSUPPORTED")
    assert len(diag) == 1 and diag[0]["side"] == "BEFORE" and diag[0]["params"]["reason"] == reason
    assert not diagnostics(result, "DEVICE_ROWS_UNASSIGNED")
    assert not diagnostics(result, "DEVICE_TAB_FACTS_UNAVAILABLE")


@pytest.mark.parametrize("excluded", [frozenset({"BEFORE"}), frozenset({"BEFORE", "CURRENT"})])
def test_identity_exclusion_reports_each_existing_affected_side(excluded: frozenset[str]) -> None:
    source = side(({"dev_addr": 49},))
    shared = table("device_st", source, source, identity_excluded_sides=excluded)
    devs = ({"dev_addr": 49, "gid": 7},)
    result = build(device(devs, devs), shared)
    assert {d["side"] for d in diagnostics(result, "DEVICE_FILTER_VALUE_UNSUPPORTED")} == excluded


def test_no_device_keeps_orphan_and_empty_schema_tables_reachable() -> None:
    empty = table("device_st", side(), side(), table_change=True)
    orphan = table("device_cfg", None, side(({"gid": 7},), column="gid"), table_change=True)
    result = build(empty, orphan)
    assert all(tabs(result, name)[0]["row_filter"] is None for name in ("device_st", "device_cfg"))
    assert result.document["groups"][4]["items"] == []
    assert diagnostics(result, "DEVICE_ROWS_UNASSIGNED")[0]["params"]["row_count"] == 1


def test_missing_identity_column_keeps_unknown_count_and_fallback_tabs() -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    shared = table("device_st", side(({"x": 1},), columns={"x": "INT"}), side(({"dev_addr": 49},)))
    result = build(device(devs, devs), shared)
    assert tabs(result, "device_st")[0]["facts"]["before_row_count"] is None
    assert diagnostics(result, "DEVICE_TAB_COUNT_UNKNOWN")[0]["side"] == "BEFORE"


def test_replacement_isolates_filter_values_labels_and_unsupported_side() -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    shared = table("device_st", side(({"dev_addr": 9007199254740992},), sql_type="BIGINT", label="旧"), side(({"dev_addr": 49},), label="新"))
    result = build(device(devs, devs), shared, replacement=True)
    assert result.document["groups"] == []
    assert tabs(result, "device_st", replacement_side="before")[0]["row_filter"] is None
    current = tabs(result, "device_st", replacement_side="current")[0]
    assert current["row_filter"] == {"before": None, "current": {"column": "dev_addr", "values": [49]}}
    assert current["facts"] is None
    assert not diagnostics(result, "DEVICE_TAB_FACTS_UNAVAILABLE")
    assert all(d["side"] is not None for d in result.diagnostics["diagnostics"])


def test_channel_empty_sg_schema_change_and_global_claim_priority() -> None:
    row: dict[str, Scalar] = {"board": 1, "link_no": 2, "exe": "iec104", "tab_num": 1, "channel_desc": "通道"}
    net = table("net_cfg", None, side((row,), columns={"board": "INT"}))
    sg = table("b1_n2_sg_cfg", None, side(label="定值"), table_change=True)
    app = table("app_cfg", None, side(({"app_name": "重复", "table_cfg": sg.table_name},)))
    result = build(net, sg, app, table("unrelated", None, side()))
    assert result.document["groups"][0]["items"][0]["tabs"][0]["table_id"] == sg.table_id
    assert len(tabs(result, sg.table_id)) == 1
    assert diagnostics(result, "APP_TABLE_CFG_DUPLICATE")
    assert result.document["groups"][4]["items"][0]["item_key"] == "table:unrelated"


def test_unclaimed_channel_table_and_absent_replacement_side() -> None:
    result = build(table("b2_n3_sg_cfg", None, side()), replacement=True)
    assert result.document["replacement_sides"]["before"] == []
    diagnostic = diagnostics(result, "CHANNEL_TABLE_UNCLAIMED")[0]
    assert diagnostic["side"] == "CURRENT" and diagnostic["target"]["group_key"] == "OTHER_TABLES"


def test_shared_gid_counts_union_without_duplicating_rows() -> None:
    devs = ({"dev_addr": 49, "gid": 7}, {"dev_addr": 50, "gid": 7})
    source = side(({"gid": 7}, {"gid": 8}), column="gid")
    result = build(device(devs, devs), table("device_cfg", source, source))
    assert [t["facts"]["current_row_count"] for t in tabs(result, "device_cfg")] == [1, 1]
    assert all(d["params"]["row_count"] == 1 for d in diagnostics(result, "DEVICE_ROWS_UNASSIGNED"))


def test_composite_claims_one_whole_point_table_and_filters_other_points() -> None:
    devs = ({"dev_addr": 65532, "gid": 1},)
    source = side(({"dev_addr": 65532},))
    result = build(device(devs, devs), table("composite_signal_point", source, source), table("device_st", source, source))
    item = next(i for i in result.document["groups"][1]["items"] if i["item_key"] == "device:composite")
    assert [t["row_filter"] is None for t in item["tabs"]] == [True, False]


INVALID_NAVIGATION_MUTATIONS = (
    lambda d: d.update(contract_version="old"),
    lambda d: d["groups"].pop(),
    lambda d: d["groups"][1]["items"][1]["tabs"][0].update(row_filter={"column": "dev_addr", "value": 49}),
    lambda d: d["groups"][1]["items"][1]["tabs"][0]["row_filter"]["current"].update(values=[49, 49]),
    lambda d: d["groups"][1]["items"][1]["tabs"][0]["row_filter"]["current"].update(values=[True]),
    lambda d: d["groups"][1]["items"][1]["tabs"][0]["row_filter"]["current"].update(values=[9007199254740992]),
    lambda d: d["groups"][1]["items"][1]["tabs"][0]["facts"].update(basis="TABLE_FALLBACK", change_kind="UNCHANGED"),
)


@pytest.mark.parametrize("mutate", INVALID_NAVIGATION_MUTATIONS)
def test_strict_navigation_rejects_legacy_and_malformed_shapes(mutate: Any) -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    source = side(({"dev_addr": 49},))
    document = deepcopy(build(device(devs, devs), table("device_st", source, source)).document)
    mutate(document)
    with pytest.raises(ValueError):
        validate_navigation(document, replacement=False)


def test_diagnostics_must_match_fallback_and_targets() -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    source = side(({"dev_addr": 49},))
    shared = replace(table("device_st", source, source), evidence=evidence(degraded=True))
    result = build(device(devs, devs), shared)
    doc = deepcopy(result.diagnostics)
    doc["diagnostics"][0]["target"]["table_id"] = "absent"
    with pytest.raises(ValueError):
        validate_diagnostics(doc, result.document, frozenset({"device", "device_st"}))


@pytest.mark.parametrize("sql_type,value", [("VARCHAR(20)", "049"), ("TEXT", "49"), ("BIGINT UNSIGNED", 49), ("INT", None)])
def test_scalar_eligibility_uses_declared_type(sql_type: str, value: Scalar) -> None:
    assert scalar_reason(sql_type, value) is None


@pytest.mark.parametrize("sql_type,value", [("INT", "49"), ("TINYINT", 256), ("INT UNSIGNED", -1), ("TEXT", 49)])
def test_mismatched_scalar_is_a_decode_error(sql_type: str, value: Scalar) -> None:
    with pytest.raises(ValueError):
        scalar_reason(sql_type, value)


def test_linear_scan_and_bound_do_not_index_orphan_identities() -> None:
    source = side(tuple({"dev_addr": n} for n in range(10000)))
    result = build(table("device_st", None, source))
    assert result.scanned_rows == 10000
    assert diagnostics(result, "DEVICE_ROWS_UNASSIGNED")[0]["params"]["row_count"] == 10000
    with pytest.raises(ValueError, match="RESOURCE_LIMIT_EXCEEDED"):
        build_navigation((table("device_st", None, source),), check=lambda: None, reserve=lambda _: nullcontext(), max_state_bytes=1)


ELIGIBILITY_CASES = (
    (False, (), (), "NONE", True),
    (True, (), (), "NONE", True),
    (False, ("dev_addr",), (), "COLUMNS_ADDED", False),
    (True, ("dev_addr",), (), "COLUMNS_ADDED", False),
    (True, (), ("dev_addr",), "INCOMPATIBLE", False),
    (False, (), ("dev_addr",), "INCOMPATIBLE", False),
)


@pytest.mark.parametrize("keyed,excluded,incompatible,evolution,eligible", ELIGIBILITY_CASES)
def test_actual_keyed_and_keyless_native_identity_frame(
    keyed: bool, excluded: tuple[str, ...], incompatible: tuple[str, ...], evolution: str, eligible: bool,
) -> None:
    from gateway_backend.capabilities.business_navigation import identity_excluded_sides
    from gateway_backend.capabilities.comparison.contracts import (
        ArtifactScope, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
        SchemaEvolution, TableComparisonTask, _ComparisonTablePolicy,
    )
    from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotColumnDescriptor
    from tests.support.storage_projection import table_descriptor

    descriptor = table_descriptor("device_st", (SnapshotColumnDescriptor("dev_addr", "dev_addr", False, "INT"), SnapshotColumnDescriptor("id", "id", False, "INT")), primary_key_columns=("id",) if keyed else (), row_count=0)
    key = ("id",) if keyed else ()
    policy = _ComparisonTablePolicy("device_st", compare_excluded_columns=excluded, effective_key_before=key, effective_key_current=key)
    task = TableComparisonTask("device_st", descriptor, descriptor, None, None, ArtifactScope.ALL_CHANGES, policy)
    fact = ComparisonTableFact("device_st", ComparisonTableStatus.UNCHANGED, descriptor, descriptor, schema_changes=ComparisonSchemaChanges(selected_columns=("dev_addr", "id"), effective_compare_key_before=key, effective_compare_key_current=key, incompatible_columns=incompatible, schema_evolution=SchemaEvolution(evolution)))
    assert identity_excluded_sides(task, fact, "dev_addr") == (frozenset() if eligible else frozenset({"BEFORE", "CURRENT"}))


def test_typed_table_and_comparison_risk_reduction_excludes_row_events() -> None:
    from gateway_backend.capabilities.business_navigation import reduce_table_risks
    from gateway_backend.capabilities.risk_evaluation.contracts import (
        RiskAnnotation, RiskReason, RiskReasonCode, RiskRuleId, RiskTarget, RiskTargetType,
    )
    reason = RiskReason(next(iter(RiskReasonCode)), "reason", next(iter(RiskRuleId)))
    events = (
        RiskAnnotation("row", RiskLevel.HIGH, RiskTarget(RiskTargetType.ROW, table_name="a"), (reason,)),
        RiskAnnotation("table", RiskLevel.MEDIUM_LOW, RiskTarget(RiskTargetType.TABLE, table_name="a"), (reason,)),
        RiskAnnotation("targeted", RiskLevel.MEDIUM_HIGH, RiskTarget(RiskTargetType.COMPARISON, table_name="b"), (reason,)),
        RiskAnnotation("global", RiskLevel.UNKNOWN, RiskTarget(RiskTargetType.COMPARISON), (reason,)),
    )
    assert reduce_table_risks(("a", "b", "c"), events) == {"a": RiskLevel.UNKNOWN, "b": RiskLevel.MEDIUM_HIGH, "c": RiskLevel.UNKNOWN}
    assert reduce_table_risks(("a", "b", "c"), iter(events)) == reduce_table_risks(("a", "b", "c"), events)


def test_unchanged_shared_table_never_opens_before_row_stream() -> None:
    def forbidden() -> Any:
        raise AssertionError("unchanged before stream must remain unopened")
    devs = ({"dev_addr": 49, "gid": 7},)
    old = NavigationSide({"dev_addr": "INT"}, forbidden, 1, "表")
    new = side(({"dev_addr": 49},))
    result = build(device(devs, devs), table("device_st", old, new, unchanged=True))
    assert tabs(result, "device_st")[0]["facts"]["before_row_count"] == 1
    assert result.scanned_rows == 3  # two tiny registry sides + current shared side


def test_protocol_diagnostic_targets_existing_empty_channel_item() -> None:
    row: dict[str, Scalar] = {"board": 1, "link_no": 2, "exe": "dev103"}
    result = build(table("net_cfg", None, side((row,))))
    items = result.document["groups"][2]["items"]
    assert items[1]["item_key"] == "protocol:b1_n2" and items[1]["tabs"] == []
    diagnostic = diagnostics(result, "PROTOCOL_TABLE_NOT_FOUND")[0]
    assert diagnostic["target"]["item_key"] == "protocol:b1_n2"
    assert diagnostic["params"]["expected_tables"] == ["b1_n2_nr103d_cfg", "b1_n2_nr103d_dev_cfg"]


def test_unrecorded_identity_requires_two_sides_and_actual_eligibility() -> None:
    source = side(({"dev_addr": 49},))
    assert not table("device_st", None, source).may_reuse_unrecorded_identity
    assert not table("device_st", source, source, identity_excluded_sides=frozenset({"BEFORE"})).may_reuse_unrecorded_identity
    assert table("device_st", source, source).may_reuse_unrecorded_identity


def test_suppressed_additions_do_not_fabricate_before_identity() -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    old = side()
    current = side(({"dev_addr": 49},))
    shared = replace(table("device_st", old, current), evidence=evidence(suppressed_added_count=1))
    result = build(device(devs, devs), shared)
    facts = tabs(result, "device_st")[0]["facts"]
    assert facts["basis"] == "TABLE_FALLBACK" and facts["before_row_count"] == 0
    assert not shared.may_reuse_unrecorded_identity


def test_cancellation_propagates_and_memory_reservation_closes() -> None:
    from contextlib import contextmanager
    from collections.abc import Iterator
    released: list[bool] = []
    @contextmanager
    def reserve(size: int) -> Iterator[object]:
        assert size > 16 * 1024 * 1024
        try:
            yield object()
        finally:
            released.append(True)
    calls = 0
    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls > 2:
            raise RuntimeError("cancelled")
    source = side(({"dev_addr": 49},))
    with pytest.raises(RuntimeError, match="cancelled"):
        build_navigation((table("device_st", None, source),), check=cancel, reserve=reserve)
    assert released == [True]
