"""Pure navigation Contract coverage; no repository or process fixtures."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from contextlib import ExitStack, nullcontext
from dataclasses import replace
from typing import Any

import pytest

from gateway_backend.capabilities.business_navigation import (
    FilterRecord, NavigationChangeKind, NavigationEvidence, NavigationRow, NavigationSide, NavigationTable,
    build_navigation, validate_navigation,
)
from gateway_backend.capabilities.business_navigation.contracts import (
    POINT_TABLES, Scalar, validate_diagnostics,
)
from gateway_backend.capabilities.business_navigation.producer import scalar_reason
from gateway_backend.capabilities.risk_evaluation.contracts import RiskLevel
from gateway_backend.capabilities.table_access import KernelExecutionContext, current_kernel_context
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceChangeKind

pytestmark = pytest.mark.unit


def side(rows: tuple[Mapping[str, Scalar], ...] = (), *, column: str = "dev_addr",
         sql_type: str = "INT", columns: Mapping[str, str | None] | None = None,
         label: str = "表", comment: str | None = None) -> NavigationSide:
    # Tests deliberately control canonical representative bytes independently of row order.
    data = tuple(NavigationRow(r, str(sorted(r.items())).encode()) for r in rows)
    return NavigationSide(columns or {column: sql_type}, lambda: iter(data), len(data), label, comment)


def evidence(**changes: Any) -> NavigationEvidence:
    return replace(NavigationEvidence(comparison_succeeded=True, risk_attribution_complete=True), **changes)


def table(name: str, old: NavigationSide | None, new: NavigationSide | None, **changes: Any) -> NavigationTable:
    return NavigationTable(name, name, old, new, evidence(), **changes)


def device(old: tuple[Mapping[str, Scalar], ...], new: tuple[Mapping[str, Scalar], ...]) -> NavigationTable:
    columns = {"dev_addr": "INT", "gid": "INT"}
    return table("device", side(old, columns=columns), side(new, columns=columns))


def build(*tables: NavigationTable, replacement: bool = False) -> Any:
    return build_navigation(tables, replacement=replacement, check=lambda: None, reserve=lambda _: nullcontext(), resources=ExitStack())


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
    ({"schema_only": True}, "TABLE_DEGRADED"),
    ({"degraded": True}, "TABLE_DEGRADED"),
)


@pytest.mark.parametrize("changes,reason", FALLBACK_CASES)
def test_incomplete_records_never_report_exact(changes: dict[str, Any], reason: str) -> None:
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
    assert not shared.may_reuse_unrecorded_identity


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
    changes = [t["facts"]["row_changes"] for t in tabs(result, "device_st")]
    assert [(c["modified"], c["moved_out"], c["moved_in"]) for c in changes] == [(1, 1, 0), (1, 0, 1)]


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


@pytest.mark.parametrize("value", (9007199254740992, -9007199254740992))
def test_unrepresentable_identity_in_unchanged_table_reports_both_sides(value: int) -> None:
    source = side(({"dev_addr": 49}, {"dev_addr": value}), sql_type="BIGINT")
    shared = table("device_st", source, source, unchanged=True)
    devs = ({"dev_addr": 49, "gid": 7},)
    result = build(device(devs, devs), shared)
    assert tabs(result, "device_st")[0]["row_filter"] is None
    diag = diagnostics(result, "DEVICE_FILTER_VALUE_UNSUPPORTED")
    assert {entry["side"] for entry in diag} == {"BEFORE", "CURRENT"}
    assert all(entry["params"]["reason"] == "INTEGER_OUT_OF_RANGE" for entry in diag)
    assert not diagnostics(result, "DEVICE_ROWS_UNASSIGNED")


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
    assert not shared.may_reuse_unrecorded_identity


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
    sg = table("b1_n2_sg_cfg", None, side(label="定值", comment="定值引用表"), table_change=True)
    app = table("app_cfg", None, side(({"app_name": "重复", "table_cfg": sg.table_name},)))
    result = build(net, sg, app, table("unrelated", None, side()))
    assert result.document["groups"][0]["items"][0]["tabs"][0]["table_id"] == sg.table_id
    assert len(tabs(result, sg.table_id)) == 1
    assert diagnostics(result, "APP_TABLE_CFG_DUPLICATE")
    assert result.document["groups"][4]["items"][0]["item_key"] == "table:unrelated"


def test_unclaimed_channel_table_and_absent_replacement_side() -> None:
    result = build(table("b2_n3_sg_cfg", None, side(comment="定值引用表")), replacement=True)
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
    lambda d: d["groups"][1]["items"][1]["tabs"][0].pop("empty"),
    lambda d: d["groups"][1]["items"][1]["tabs"][0].update(empty=0),
    lambda d: d["groups"][1]["items"][1]["summary"].update(nonempty_tab_count=99),
    lambda d: d["groups"][1]["items"][1]["summary"].update(change_kinds=["UNKNOWN_SURFACE_KIND"]),
    lambda d: d["groups"][1].update(nonempty_item_count=99),
    lambda d: d["groups"][1]["items"][1]["tabs"][0].update(extra=True),
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
        build_navigation((table("device_st", None, source),), check=lambda: None, reserve=lambda _: nullcontext(), resources=ExitStack(), max_state_bytes=1)


ELIGIBILITY_CASES = (
    (False, (), (), "NONE", True),
    (True, (), (), "NONE", True),
    (False, ("dev_addr",), (), "COLUMNS_ADDED", False),
    (True, ("dev_addr",), (), "COLUMNS_ADDED", False),
    (True, (), ("dev_addr",), "INCOMPATIBLE", False),
    (True, ("id",), (), "NONE", False),
    (True, (), ("id",), "INCOMPATIBLE", False),
    (False, (), ("dev_addr",), "INCOMPATIBLE", False),
)


@pytest.mark.parametrize("identity_column", ["dev_addr", "gid"])
@pytest.mark.parametrize("keyed,excluded,incompatible,evolution,eligible", ELIGIBILITY_CASES)
def test_actual_keyed_and_keyless_native_identity_frame(
    keyed: bool, excluded: tuple[str, ...], incompatible: tuple[str, ...], evolution: str, eligible: bool, identity_column: str,
) -> None:
    from gateway_backend.capabilities.business_navigation import identity_excluded_sides
    from gateway_backend.capabilities.comparison.contracts import (
        ArtifactScope, ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
        KeylessPolicy, SchemaEvolution, TableComparisonTask, _ComparisonTablePolicy,
    )
    from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotColumnDescriptor
    from tests.support.storage_projection import table_descriptor

    excluded = tuple(identity_column if c == "dev_addr" else c for c in excluded)
    incompatible = tuple(identity_column if c == "dev_addr" else c for c in incompatible)
    descriptor = table_descriptor("device_st", (SnapshotColumnDescriptor(identity_column, identity_column, False, "INT"), SnapshotColumnDescriptor("id", "id", False, "INT")), primary_key_columns=("id",) if keyed else (), row_count=0)
    key = ("id",) if keyed else ()
    policy = _ComparisonTablePolicy("device_st", compare_excluded_columns=excluded, effective_key_before=key, effective_key_current=key, keyless_policy=KeylessPolicy.FULL_ROW_DIGEST_SET_DIFF)
    task = TableComparisonTask("device_st", descriptor, descriptor, None, None, ArtifactScope.ALL_CHANGES, policy)
    fact = ComparisonTableFact("device_st", ComparisonTableStatus.UNCHANGED, descriptor, descriptor, schema_changes=ComparisonSchemaChanges(selected_columns=tuple(sorted((identity_column, "id"))), effective_compare_key_before=key, effective_compare_key_current=key, incompatible_columns=incompatible, schema_evolution=SchemaEvolution(evolution)))
    assert identity_excluded_sides(task, fact, identity_column) == (frozenset() if eligible else frozenset({"BEFORE", "CURRENT"}))
    if not keyed:
        inactive = replace(task, policy=replace(policy, keyless_policy=KeylessPolicy.DEGRADE_NO_COMPARE_KEY))
        assert identity_excluded_sides(inactive, fact, identity_column) == frozenset({"BEFORE", "CURRENT"})


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
    assert items[1]["attributes"] == {"board": 1, "link_no": 2, "protocol": "dev103"}
    diagnostic = diagnostics(result, "PROTOCOL_TABLE_NOT_FOUND")[0]
    assert diagnostic["target"]["item_key"] == "protocol:b1_n2"
    assert diagnostic["params"]["expected_prefixes"] == ["b1_n2_nr103d"]


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
        build_navigation((table("device_st", None, source),), check=cancel, reserve=reserve, resources=ExitStack())
    assert released == [True]


def test_many_shared_gid_rows_aggregate_without_per_device_record_state() -> None:
    devs = tuple({"dev_addr": n, "gid": 7} for n in range(100))
    source = side(tuple({"gid": 7} for _ in range(1000)), column="gid")
    records = tuple(FilterRecord(str(n), "ROW_MODIFIED", {"gid": 7}, {"gid": 7}, RiskLevel.LOW) for n in range(1000))
    shared = replace(table("device_cfg", source, source), evidence=evidence(records=records, expected_record_counts=(0, 0, 1000), locator_complete=True))
    result = build_navigation((device(devs, devs), shared), check=lambda: None, reserve=lambda _: nullcontext(), resources=ExitStack(), max_state_bytes=300000)
    assert len(tabs(result, "device_cfg")) == 100
    assert all(t["facts"]["current_row_count"] == 1000 and t["facts"]["risk_level"] == "LOW" for t in tabs(result, "device_cfg"))
    # The parents and appended tabs must still consume the same bounded budget.
    with ExitStack() as resources, pytest.raises(ValueError, match="RESOURCE_LIMIT_EXCEEDED"):
        build_navigation((device(devs, devs), shared), check=lambda: None,
                         reserve=lambda _: nullcontext(), resources=resources,
                         max_state_bytes=100000)


@pytest.mark.parametrize("name,values,columns", [
    ("device", {"dev_addr": 49, "gid": 7}, {"dev_addr": "INT", "gid": "INT"}),
    ("net_cfg", {"board": 1, "link_no": 2, "exe": "dev103"}, {"board": "INT"}),
    ("app_cfg", {"table_cfg": "missing", "app_name": "参数"}, {"table_cfg": "TEXT"}),
])
def test_unchanged_registry_never_opens_before_stream(
    name: str, values: Mapping[str, Scalar], columns: Mapping[str, str | None],
) -> None:
    def forbidden() -> Any:
        raise AssertionError("unchanged registry before stream must remain unopened")
    old = NavigationSide(columns, forbidden, 1, "表")
    build(table(name, old, side((values,), columns=columns), unchanged=True))


@pytest.mark.parametrize("name,column", [("device_st", "dev_addr"), ("device_cfg", "gid")])
@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("affected", ["BEFORE", "CURRENT"])
def test_registry_to_target_category_mismatch_downgrades_only_affected_side(
    name: str, column: str, replacement: bool, affected: str,
) -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    number = 7 if column == "gid" else 49
    sources = {label: side(({column: str(number) if label == affected else number},), column=column,
                          sql_type="TEXT" if label == affected else "INT")
               for label in ("BEFORE", "CURRENT")}
    result = build(device(devs, devs), table(name, sources["BEFORE"], sources["CURRENT"]), replacement=replacement)
    diags = diagnostics(result, "DEVICE_FILTER_VALUE_UNSUPPORTED")
    assert len(diags) == 1 and diags[0]["side"] == affected
    assert diags[0]["params"] == {"identity_column": column, "reason": "UNSUPPORTED_TYPE"}
    if replacement:
        other = "current" if affected == "BEFORE" else "before"
        assert tabs(result, name, replacement_side=affected.lower())[0]["row_filter"] is None
        assert tabs(result, name, replacement_side=other)[0]["row_filter"][other]["values"] == [number]
    else:
        assert len(tabs(result, name)) == 1 and tabs(result, name)[0]["row_filter"] is None
    assert not diagnostics(result, "DEVICE_ROWS_UNASSIGNED")


@pytest.mark.parametrize("changes,reason,may_reuse", [
    ({"risk_attribution_complete": False}, None, True),
    ({"comparison_succeeded": False}, "RECORDS_UNAVAILABLE", False),
    ({"schema_only": True}, "TABLE_DEGRADED", False),
    ({"degraded": True}, "TABLE_DEGRADED", False),
])
def test_uncertain_empty_shared_table_without_device_remains_reachable(
    changes: dict[str, Any], reason: str | None, may_reuse: bool,
) -> None:
    empty = replace(table("device_st", side(), side(), unchanged=True), evidence=evidence(**changes))
    result = build(empty)
    assert len(tabs(result, "device_st")) == 1
    assert tabs(result, "device_st")[0]["row_filter"] is None
    assert tabs(result, "device_st")[0]["facts"] is None
    assert not diagnostics(result, "DEVICE_TAB_FACTS_UNAVAILABLE")
    assert empty.local_fallback_reason == reason
    assert empty.may_reuse_unrecorded_identity is may_reuse
    if not empty.evidence.risk_attribution_complete:
        assert result.document["table_notices"][0]["risk_complete"] is False


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("has_other_device", [False, True])
def test_virtual_composite_filters_existing_shared_side_without_registry_row(
    replacement: bool, has_other_device: bool,
) -> None:
    shared = table("device_st", None, side(({"dev_addr": 65532},)))
    composite = table("composite_signal_point", None, side())
    inputs: tuple[NavigationTable, ...] = (shared, composite)
    if has_other_device:
        inputs += (device((), ({"dev_addr": 49, "gid": 7},)),)
    result = build(*inputs, replacement=replacement)
    groups = result.document["replacement_sides"]["current"] if replacement else result.document["groups"]
    item = next(i for i in groups[1]["items"] if i["item_key"] == "device:composite")
    point = next(t for t in item["tabs"] if t["table_id"] == "device_st")
    assert point["row_filter"] == {"before": None, "current": {"column": "dev_addr", "values": [65532]}}
    assert not diagnostics(result, "DEVICE_ROWS_UNASSIGNED")
    assert all(t["table_id"] != "device_cfg" for t in item["tabs"])


def test_large_full_row_keys_cannot_bypass_existing_operation_admission() -> None:
    emitted: list[int] = []
    def rows() -> Any:
        for board in range(64):
            emitted.append(board)
            yield NavigationRow({"board": board, "link_no": 1, "exe": "iec104", "tab_num": 1}, bytes([board]) * 1024 * 1024)
    source = NavigationSide({"board": "INT"}, rows, 64, "net")
    with ExitStack() as resources, pytest.raises(ValueError, match="RESOURCE_LIMIT_EXCEEDED"):
        build_navigation((table("net_cfg", None, source),), check=lambda: None,
                         reserve=lambda _: nullcontext(), resources=resources)
    assert len(emitted) < 64


@pytest.mark.parametrize("name", ["net_cfg", "device", "app_cfg"])
def test_replacing_large_representative_releases_old_state_charge(name: str) -> None:
    if name == "net_cfg":
        values: Mapping[str, Scalar] = {"board": 1, "link_no": 2, "exe": "iec104", "tab_num": 1}
        column_types: Mapping[str, str | None] = {"board": "INT"}
        other: tuple[NavigationTable, ...] = ()
    elif name == "device":
        values = {"dev_addr": 49, "gid": 7}
        column_types = {"dev_addr": "INT", "gid": "INT"}
        other = ()
    else:
        values = {"table_cfg": "target", "app_name": "app"}
        column_types = {"table_cfg": "TEXT"}
        other = (table("target", None, side()),)
    def rows() -> Any:
        for n in range(64, 0, -1):
            yield NavigationRow(values, bytes([n]) * 1024 * 1024)
    source = NavigationSide(column_types, rows, 64, name)
    with ExitStack() as resources:
        result = build_navigation((table(name, None, source), *other), check=lambda: None,
                                  reserve=lambda _: nullcontext(), resources=resources,
                                  max_state_bytes=2 * 1024 * 1024)
        assert result.scanned_rows == 64
        assert result.to_bytes()


def test_result_and_cached_wire_bytes_keep_original_operation_admission() -> None:
    from contextlib import contextmanager
    from collections.abc import Iterator
    active: list[int] = []
    @contextmanager
    def reserve(size: int) -> Iterator[object]:
        active.append(size)
        try:
            yield object()
        finally:
            active.pop()
    with ExitStack() as resources:
        result = build_navigation((table("other", None, side()),), check=lambda: None,
                                  reserve=reserve, resources=resources)
        assert active
        first = result.to_bytes()
        assert result.to_bytes() is first
    assert active == []


# One owner for zero-side, table-level and original-structure empty semantics.
EMPTY_TABLE_CASES = (
    (None, 0, False, False, True),
    (0, None, False, False, True),
    (0, 0, False, False, True),
    (None, None, False, False, False),
    (0, 1, False, False, False),
    (1, 0, False, False, False),
    (0, 0, True, False, False),
    (0, 0, False, True, False),
)


@pytest.mark.parametrize("kind", (SurfaceChangeKind.ADDED, SurfaceChangeKind.DELETED, SurfaceChangeKind.DEGRADED))
@pytest.mark.parametrize("old,new,structure,replacement,empty", EMPTY_TABLE_CASES)
def test_empty_marks_existing_zero_sides_without_deleting_audit_tabs(
    old: int | None, new: int | None, structure: bool, replacement: bool, empty: bool, kind: SurfaceChangeKind,
) -> None:
    shared = replace(table("other", None if old is None else side(tuple({} for _ in range(old))),
        None if new is None else side(tuple({} for _ in range(new))), table_change=True,
        structure_changed=structure, change_kind=NavigationChangeKind(kind.value), risk_level=RiskLevel.HIGH),
        evidence=evidence(degraded=True, table_risk=RiskLevel.HIGH))
    result = build(shared, replacement=replacement)
    if replacement:
        tab = tabs(result, "other", replacement_side="current")[0]
        group = result.document["replacement_sides"]["current"][4]
    else:
        tab = tabs(result, "other")[0]
        group = result.document["groups"][4]
    assert tab["empty"] is empty
    assert group["nonempty_item_count"] == int(not empty)
    summary = group["items"][0]["summary"]
    assert summary == {"change_kinds": [] if empty else [kind.value],
                       "risk_level": None if empty else "HIGH", "nonempty_tab_count": int(not empty),
                       "change_complete": True, "risk_complete": True}


@pytest.mark.parametrize("fallback", (False, True))
def test_filtered_zero_tab_ignores_other_device_changes_and_table_risks(fallback: bool) -> None:
    devs = ({"dev_addr": 49, "gid": 7}, {"dev_addr": 50, "gid": 8})
    source = side(({"dev_addr": 49},))
    record = FilterRecord("row", "ROW_MODIFIED", {"dev_addr": 49}, {"dev_addr": 49}, RiskLevel.LOW)
    shared = replace(table("device_st", source, source, table_change=True,
        change_kind=NavigationChangeKind.UPDATED, risk_level=RiskLevel.HIGH),
        evidence=evidence(records=(record,), expected_record_counts=(0, 0, 1), locator_complete=True,
                          degraded=fallback, table_risk=RiskLevel.HIGH))
    result = build(device(devs, devs), shared)
    marked = tabs(result, "device_st")
    assert [t["empty"] for t in marked] == [False, True]
    items = result.document["groups"][1]["items"]
    populated = next(i for i in items if i["item_key"] == "device:addr:49")
    all_empty = next(i for i in items if i["item_key"] == "device:addr:50")
    assert populated["summary"]["risk_level"] == "LOW"
    assert all_empty["summary"] == {"change_kinds": [], "risk_level": None, "nonempty_tab_count": 0, "change_complete": True, "risk_complete": True}
    assert len(marked) == 2  # Audit and browsing keep the empty tab, even under fallback.


@pytest.mark.parametrize("missing", ("before", "current"))
def test_existing_side_with_unknown_filtered_count_is_not_assumed_zero(missing: str) -> None:
    devs = ({"dev_addr": 49, "gid": 7},)
    known, unknown = side(), side(columns={"other": "INT"})
    shared = table("device_st", unknown if missing == "before" else known,
                   unknown if missing == "current" else known)
    result = build(device(devs, devs), shared)
    tab = tabs(result, "device_st")[0]
    assert tab["facts"][missing + "_row_count"] is None
    assert not tab["empty"]
    assert len(diagnostics(result, "DEVICE_TAB_COUNT_UNKNOWN")) == 1


def test_empty_forward_channel_and_unassigned_shared_table_remain_reachable() -> None:
    registry: dict[str, Scalar] = {"board": 1, "link_no": 2, "exe": "iec104", "tab_num": 1}
    result = build(table("net_cfg", None, side((registry,))),
        table("b1_n2_iec104_syx_list", side(comment="遥信引用表"), side(comment="遥信引用表"), unchanged=True),
        table("device_st", side(), side(), unchanged=True))
    channel = result.document["groups"][0]
    assert channel["nonempty_item_count"] == 0 and len(channel["items"]) == 1
    assert channel["items"][0]["tabs"][0]["empty"]
    assert tabs(result, "device_st")[0]["row_filter"] is None
    assert tabs(result, "device_st")[0]["empty"]


def test_navigation_change_vocabulary_matches_its_surface_owner() -> None:
    assert {kind.value for kind in NavigationChangeKind} == {kind.value for kind in SurfaceChangeKind}


@pytest.mark.parametrize("kind", tuple(SurfaceChangeKind))
def test_nonempty_navigation_summary_preserves_every_surface_change_kind(kind: SurfaceChangeKind) -> None:
    source = side(({},))
    result = build(table("other", source, source, change_kind=NavigationChangeKind(kind.value)))
    summary = result.document["groups"][4]["items"][0]["summary"]
    assert summary == {"change_kinds": [kind.value], "risk_level": None, "nonempty_tab_count": 1, "change_complete": True, "risk_complete": True}
    validate_navigation(result.document, replacement=False)


APP_PARAMETER_CASES = (
    ("0:NO", "missing", False), ("0:NO", "", False), ("0:NO", None, False),
    ("1:YES", "missing", True), ("1:YES", "", True), (None, "missing", True),
)


@pytest.mark.parametrize("logical_side", ("BEFORE", "CURRENT"))
@pytest.mark.parametrize("enable,target,warns", APP_PARAMETER_CASES)
def test_disabled_app_missing_parameter_table_is_expected(
    logical_side: str, enable: Scalar, target: Scalar, warns: bool,
) -> None:
    source = side(({'app_name': 'JMS', 'table_cfg': target, 'enable': enable},))
    app = table("app_cfg", source if logical_side == "BEFORE" else None,
                source if logical_side == "CURRENT" else None)
    result = build(app)
    notes = diagnostics(result, "APP_TABLE_NOT_FOUND") + diagnostics(result, "APP_TABLE_CFG_MISSING")
    assert bool(notes) is warns
    if warns:
        assert notes[0]["side"] == logical_side


def test_disabled_app_existing_parameter_table_stays_browsable() -> None:
    source = side(({'app_name': 'JMS', 'table_cfg': 'jms_cfg', 'enable': '0:NO'},))
    result = build(table("app_cfg", None, source), table("jms_cfg", None, side()))
    assert tabs(result, "jms_cfg")
    assert result.diagnostics is None


def test_enabled_app_requires_parameter_table_on_its_own_side() -> None:
    source = side(({'app_name': 'JMS', 'table_cfg': 'jms_cfg', 'enable': '1:YES'},))
    result = build(table("app_cfg", source, source), table("jms_cfg", side(), None))
    assert [d["side"] for d in diagnostics(result, "APP_TABLE_NOT_FOUND")] == ["CURRENT"]


def test_network_and_serial_channels_claim_actual_tables_once() -> None:
    net = table("net_cfg", None, side(({"board": 1, "link_no": 2, "exe": "DLL"},)))
    com = table("com_cfg", None, side(({"board": 1, "com_no": 2, "exe": "stdmdsCOM", "channel_desc": "串口"},), comment="串口配置"))
    result = build(net, com,
        table("b01_n02_dll3xx_extra", None, side(comment="网络一")),
        table("b1_n2_dll495", None, side(comment="网络二")),
        table("b1_c2_stdmds_any", None, side(comment="串口规约")),
        table("b1_c2_custom", None, side(comment="遥信引用表")))
    groups = result.document["groups"]
    assert [i["item_key"] for i in groups[2]["items"]] == [
        "protocol:table", "protocol:com_cfg", "protocol:b1_n2", "protocol:b1_c2"]
    assert [t["label"] for t in groups[2]["items"][2]["tabs"]] == ["网络一", "网络二"]
    assert groups[0]["items"][0]["tabs"][0]["label"] == "遥信"
    assert len(tabs(result, "b1_c2_custom")) == 1
    assert not diagnostics(result, "PROTOCOL_TABLE_NOT_FOUND")


def test_current_comment_controls_pair_classification_and_replacement_is_independent() -> None:
    row: dict[str, str | int | None] = {"board": 1, "com_no": 2, "exe": "x"}
    registry = table("com_cfg", side((row,)), side((row,)))
    target = table("b1_c2_x_more", side(comment="旧引用表"), side(comment=None))
    result = build(registry, target)
    assert not result.document["groups"][0]["items"]
    assert tabs(result, target.table_id)[0]["label"] == target.table_name
    replacement = build(registry, target, replacement=True)
    assert replacement.document["replacement_sides"]["before"][0]["items"]
    assert not replacement.document["replacement_sides"]["current"][0]["items"]


def test_empty_exe_and_orphan_serial_reference_remain_browsable() -> None:
    registry = table("com_cfg", None, side(({"board": 1, "com_no": 2, "exe": "  "},)))
    target = table("b1_c2_any", None, side(comment="引用表"))
    result = build(registry, target)
    assert not result.document["groups"][2]["items"]
    assert len(tabs(result, "com_cfg")) == len(tabs(result, target.table_id)) == 1
    assert diagnostics(result, "CHANNEL_TABLE_UNCLAIMED")[0]["params"] == {
        "channel_prefix": "b1_c2", "registry_table": "com_cfg"}


@pytest.mark.parametrize("kind,exe,segment", [
    ("n", "dev103", "nr103d"), ("n", "ht103", "nr103ht"),
    ("n", "ModbusNetDev", "modbusnet"), ("n", "stdmdsNET", "stdmds"),
    ("n", "dev103_9150", "nrts103"), ("n", "mach2Dev", "mach2"),
    ("n", "abb103Dev", "abb103"), ("n", "cagc", "agc"),
    ("c", "stdmdsCOM", "stdmds"), ("c", "DLL", "dll495"),
    ("c", "custom", "custom"),
])
def test_protocol_mapping_claims_literal_prefix(kind: str, exe: str, segment: str) -> None:
    registry = "net_cfg" if kind == "n" else "com_cfg"
    column = "link_no" if kind == "n" else "com_no"
    name = f"b1_{kind}2_{segment}extra"
    result = build(table(registry, None, side(({"board": 1, column: 2, "exe": exe},))),
                   table(name, None, side(comment="标签")))
    item = next(i for i in result.document["groups"][2]["items"] if i["item_key"] == f"protocol:b1_{kind}2")
    assert [t["table_id"] for t in item["tabs"]] == [name]
    assert not diagnostics(result, "PROTOCOL_TABLE_NOT_FOUND")


def test_navigation_v4_rejects_old_diagnostic_shape_and_version() -> None:
    result = build(table("com_cfg", None, side(({"board": 1, "com_no": 2, "exe": "x"},))))
    old_navigation = deepcopy(result.document)
    old_navigation["contract_version"] = "backend-vnext/business-navigation/v3"
    with pytest.raises(ValueError):
        validate_navigation(old_navigation, replacement=False)
    old_diagnostics = deepcopy(result.diagnostics)
    assert old_diagnostics is not None
    old_diagnostics["diagnostics"][0]["params"] = {"board": 1, "link_no": 2, "protocol": "x", "expected_tables": []}
    with pytest.raises(ValueError):
        validate_diagnostics(old_diagnostics, result.document, frozenset({"com_cfg"}))


def test_channel_representatives_and_side_ownership_do_not_cross() -> None:
    old: tuple[dict[str, str | int | None], ...] = ({"board": 3, "com_no": 4, "exe": "old", "channel_desc": "旧"},)
    current: tuple[dict[str, str | int | None], ...] = ({"board": 3, "com_no": 4, "exe": " "},
               {"board": 3, "com_no": 4, "exe": "new", "channel_desc": "新"})
    registry = table("com_cfg", side(old), side(current))
    old_only = table("b3_c4_old_extra", side(comment="旧表"), None)
    new_only = table("b3_c4_new_extra", None, side(comment="新表"))
    result = build(registry, old_only, new_only)
    item = next(i for i in result.document["groups"][2]["items"] if i["item_key"] == "protocol:b3_c4")
    assert item["label"] == "新"
    assert [t["table_id"] for t in item["tabs"]] == [new_only.table_id, old_only.table_id]
    assert not diagnostics(result, "PROTOCOL_TABLE_NOT_FOUND")


def test_reference_without_registration_cannot_be_claimed_by_app_cfg() -> None:
    reference = table("b2_c3_any", None, side(comment="引用表"))
    app = table("app_cfg", None, side(({"app_name": "应用", "table_cfg": reference.table_name},)))
    result = build(reference, app)
    assert result.document["groups"][4]["items"][0]["item_key"] == "table:b2_c3_any"
    assert len(tabs(result, reference.table_id)) == 1
    assert diagnostics(result, "CHANNEL_TABLE_UNCLAIMED")[0]["side"] == "CURRENT"


@pytest.mark.parametrize("kind,missing", [("n", "CURRENT"), ("n", "BEFORE"), ("c", "CURRENT"), ("c", "BEFORE")])
def test_reference_diagnostic_reports_unregistered_side_when_other_side_claims(kind: str, missing: str) -> None:
    registry_name = "net_cfg" if kind == "n" else "com_cfg"
    column = "link_no" if kind == "n" else "com_no"
    active = side(({"board": 1, column: 2, "exe": "x"},))
    empty = side(({"board": 1, column: 2, "exe": " "},))
    registry = table(registry_name, empty if missing == "BEFORE" else active,
                     empty if missing == "CURRENT" else active)
    name = f"b1_{kind}2_ref"
    result = build(registry, table(name, side(comment="引用表"), side(comment="引用表")))
    assert len(tabs(result, name)) == 1
    diagnostic, = diagnostics(result, "CHANNEL_TABLE_UNCLAIMED")
    assert diagnostic["side"] == missing
    assert diagnostic["target"] == {"group_key": "FORWARD_CHANNELS", "item_key": f"channel:b1_{kind}2",
                                    "tab_key": None, "table_id": name}
    assert diagnostic["params"] == {"channel_prefix": f"b1_{kind}2", "registry_table": registry_name}


def test_empty_serial_registry_stays_in_other_tables_when_referenced_by_app() -> None:
    registry = table("com_cfg", None, side(({"board": 1, "com_no": 2, "exe": " "},)))
    app = table("app_cfg", None, side(({"app_name": "应用", "table_cfg": "com_cfg"},)))
    result = build(registry, app)
    assert any(item["item_key"] == "table:com_cfg" for item in result.document["groups"][4]["items"])
    assert len(tabs(result, "com_cfg")) == 1


def test_risk_incomplete_preserves_exact_change_and_known_risk() -> None:
    old = side(({"dev_addr": 49},))
    record = FilterRecord("row", "ROW_MODIFIED", {"dev_addr": 49}, {"dev_addr": 49}, RiskLevel.LOW)
    shared = replace(table("device_st", old, old), evidence=evidence(records=(record,),
        expected_record_counts=(0, 0, 1), locator_complete=True, risk_attribution_complete=False))
    result = build(device(({"dev_addr": 49, "gid": 1},), ({"dev_addr": 49, "gid": 1},)), shared)
    facts = tabs(result, "device_st")[0]["facts"]
    assert facts["basis"] == "EXACT" and facts["risk_level"] == "LOW" and not facts["risk_complete"]
    assert facts["row_changes"]["modified"] == 1
    assert diagnostics(result, "DEVICE_TAB_RISK_UNAVAILABLE")
    assert result.document["table_notices"][0]["unlocated_row_risk"]["risk_level"] is None


def test_registry_only_equal_count_exchange_marks_membership() -> None:
    old = ({"dev_addr": 49, "gid": 1}, {"dev_addr": 50, "gid": 2})
    new = ({"dev_addr": 49, "gid": 2}, {"dev_addr": 50, "gid": 1})
    source = side(({"gid": 1}, {"gid": 2}), column="gid")
    result = build(device(old, new), table("device_cfg", source, source, unchanged=True))
    facts = [tab["facts"] for tab in tabs(result, "device_cfg")]
    assert all(f["membership_changed"] and f["membership_complete"] and f["change_kind"] == "UPDATED" for f in facts)
    assert all(f["row_changes"]["modified"] == 0 for f in facts)


def test_unowned_row_risk_is_public_and_not_assigned_to_other_devices() -> None:
    source = side(({"dev_addr": 49}, {"dev_addr": 99}))
    record = FilterRecord("orphan", "ROW_MODIFIED", {"dev_addr": 99}, {"dev_addr": 99},
                          RiskLevel.HIGH, ("ROW_MODIFIED",))
    shared = replace(table("device_st", source, source), evidence=evidence(records=(record,),
        expected_record_counts=(0, 0, 1), locator_complete=True))
    result = build(device(({"dev_addr": 49, "gid": 1},), ({"dev_addr": 49, "gid": 1},)), shared)
    assert tabs(result, "device_st")[0]["facts"]["risk_level"] is None
    notice = result.document["table_notices"][0]
    assert notice["unlocated_row_risk"] == {"risk_level": "HIGH", "count": None, "reason_codes": ["ROW_MODIFIED"]}


def test_device_changes_use_actual_side_context_and_keep_original_record_identity() -> None:
    old, new = ({"dev_addr": 49, "gid": 1},), ({"dev_addr": 50, "gid": 1},)
    record = FilterRecord("device-row", "ROW_MODIFIED", {"dev_addr": 49}, {"dev_addr": 50}, RiskLevel.LOW)
    registry = replace(device(old, new), evidence=evidence(records=(record,), expected_record_counts=(0, 0, 1), locator_complete=True))
    changes = build(registry).document["device_definition_changes"]
    assert changes == [{"record_identity": "device-row", "change_kind": "UPDATED", "before_item_key": "device:addr:49",
                        "current_item_key": "device:addr:50", "before_dev_addr": 49, "current_dev_addr": 50,
                        "risk_level": "LOW", "risk_complete": True}]


def test_typed_row_pairs_and_ordered_intervals_remain_in_their_scopes(
    operation_kernel_context: KernelExecutionContext,
) -> None:
    from gateway_shared_kernel import raw_blob_digest
    from gateway_backend.application.business_presentation import RiskAttribution
    from gateway_backend.capabilities.risk_evaluation.contracts import (
        RiskAnnotation, RiskReason, RiskReasonCode, RiskRuleId, RiskTarget, RiskTargetType,
    )
    before, current = raw_blob_digest(b"before"), raw_blob_digest(b"current")
    reason = RiskReason(RiskReasonCode.ROW_MODIFIED, "modified", RiskRuleId.ROW_MODIFIED)
    pair = RiskAnnotation("pair", RiskLevel.HIGH, RiskTarget(RiskTargetType.ROW_PAIR,
        table_name="device_st", before_row_identity=before, current_row_identity=current), (reason,))
    interval = RiskAnnotation("interval", RiskLevel.LOW, RiskTarget(RiskTargetType.ROW_INTERVAL,
        table_name="ordered", position_range=(1, 3)), (reason,))
    assert current_kernel_context() is operation_kernel_context
    attribution = RiskAttribution()
    attribution.observe("device_st", (pair,), True)
    attribution.observe("ordered", (interval,), True)
    assert attribution.rows["device_st"] == {before.value: RiskLevel.HIGH, current.value: RiskLevel.HIGH}
    assert attribution.unlocated["device_st"] is None and attribution.complete["device_st"]
    assert attribution.unlocated["ordered"] is None and attribution.complete["ordered"]
