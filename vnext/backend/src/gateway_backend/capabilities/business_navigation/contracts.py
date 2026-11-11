"""Flow-neutral inputs and strict wire validation for business navigation v1.

Row identities, scalar encodings and comparison/risk facts are supplied by their owners.
This capability never reconstructs a canonical row identity from business values.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonTableFact, KeylessPolicy, SchemaEvolution, TableComparisonTask,
)
from gateway_backend.capabilities.risk_evaluation.contracts import RiskLevel

CONTRACT_VERSION = "backend-vnext/business-navigation/v1"
GROUPS = (
    ("FORWARD_CHANNELS", "转发通道"), ("SECONDARY_DEVICES", "二次装置列表"),
    ("COMMUNICATION_PROTOCOLS", "通讯规约列表"), ("GLOBAL_PARAMETERS", "全局参数"),
    ("OTHER_TABLES", "其他表"),
)
POINT_TABLES = (
    ("device_st", "状态类"), ("device_mx", "测量类"), ("device_co", "控制类"),
    ("device_sg", "定值"), ("device_sp", "装置参数"), ("device_cnt", "计量类"),
    ("device_sn", "定值区号"), ("device_tap", "档位"), ("device_other", "其它信息"),
    ("device_disturb", "扰动数据"), ("device_cfg", "装置配置"),
)
FILTER_IDENTITY_COLUMNS = {name: "gid" if name == "device_cfg" else "dev_addr" for name, _ in POINT_TABLES}
SAFE_INTEGER = 9007199254740991
Scalar: TypeAlias = str | int | None
RowValues: TypeAlias = Mapping[str, Scalar]


@dataclass(frozen=True, slots=True)
class NavigationRow:
    values: RowValues
    canonical_order_key: bytes


@dataclass(frozen=True, slots=True)
class NavigationSide:
    """A fresh bounded stream factory; absent table is represented by None.

    Column SQL spelling must come from the same-side validated descriptor, never from
    a merged surface. canonical_order_key uses the existing canonical scalar codec.
    """
    column_types: Mapping[str, str | None]
    rows: Callable[[], Iterable[NavigationRow]]
    row_count: int
    display_name: str


@dataclass(frozen=True, slots=True)
class FilterRecord:
    row_identity: str
    kind: str
    before: RowValues | None
    current: RowValues | None
    risk_level: RiskLevel | None = None

    def __post_init__(self) -> None:
        if not self.row_identity or self.kind not in {"ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"}:
            raise ValueError("invalid filter record")
        if self.kind != "ROW_ADDED" and self.before is None:
            raise ValueError("record requires before filter context")
        if self.kind != "ROW_DELETED" and self.current is None:
            raise ValueError("record requires current filter context")


@dataclass(frozen=True, slots=True)
class NavigationEvidence:
    """Proof supplied by comparison/locator/risk owners, with conservative defaults."""
    comparison_succeeded: bool = False
    schema_only: bool = False
    degraded: bool = False
    expected_record_counts: tuple[int, int, int] = (0, 0, 0)
    suppressed_added_count: int = 0
    suppressed_deleted_count: int = 0
    locator_complete: bool = False
    risk_attribution_complete: bool = False
    records: tuple[FilterRecord, ...] = ()
    table_risk: RiskLevel | None = None
    any_table_risk: bool = False

    def __post_init__(self) -> None:
        for name in ("comparison_succeeded", "schema_only", "degraded", "locator_complete", "risk_attribution_complete", "any_table_risk"):
            if type(getattr(self, name)) is not bool:
                raise ValueError("invalid navigation evidence flag")
        if type(self.expected_record_counts) is not tuple or len(self.expected_record_counts) != 3:
            raise ValueError("invalid record counts")
        for count in (*self.expected_record_counts, self.suppressed_added_count, self.suppressed_deleted_count):
            if type(count) is not int or count < 0:
                raise ValueError("invalid navigation evidence count")
        if type(self.records) is not tuple or any(type(r) is not FilterRecord for r in self.records):
            raise ValueError("invalid filter records")
        if len({r.row_identity for r in self.records}) != len(self.records):
            raise ValueError("duplicate filter record identity")
        if self.table_risk is not None and type(self.table_risk) is not RiskLevel:
            raise ValueError("invalid table risk")

    def fallback_reason(self) -> str | None:
        counts = tuple(sum(r.kind == kind for r in self.records)
                       for kind in ("ROW_ADDED", "ROW_DELETED", "ROW_MODIFIED"))
        if (not self.comparison_succeeded or counts != self.expected_record_counts
                or self.suppressed_added_count or self.suppressed_deleted_count
                or (bool(self.records) and not self.locator_complete)):
            return "RECORDS_UNAVAILABLE"
        if not self.risk_attribution_complete:
            return "RISK_ATTRIBUTION_UNAVAILABLE"
        if self.degraded or self.schema_only:
            return "TABLE_DEGRADED"
        return None

@dataclass(frozen=True, slots=True)
class NavigationTable:
    table_id: str
    table_name: str
    before: NavigationSide | None
    current: NavigationSide | None
    evidence: NavigationEvidence = field(default_factory=NavigationEvidence)
    table_change: bool = False
    unchanged: bool = False
    # Actual owner-resolved pair eligibility. Missing physical columns are distinct
    # from an existing column excluded from comparison.
    identity_excluded_sides: frozenset[str] = frozenset()

    @property
    def local_fallback_reason(self) -> str | None:
        """One effective completeness decision for omission, facts and FE12 reuse."""
        column = FILTER_IDENTITY_COLUMNS.get(self.table_name)
        if column is not None and any(
            context is not None and column not in context
            for record in self.evidence.records for context in (record.before, record.current)
        ):
            return "RECORDS_UNAVAILABLE"
        return self.evidence.fallback_reason()

    @property
    def may_reuse_unrecorded_identity(self) -> bool:
        column = FILTER_IDENTITY_COLUMNS.get(self.table_name)
        return (self.before is not None and self.current is not None and column is not None
                and column in self.before.column_types and column in self.current.column_types
                and not self.identity_excluded_sides and self.local_fallback_reason is None)

    @property
    def display_name(self) -> str:
        source = self.current or self.before
        return source.display_name if source is not None else self.table_name


def identity_excluded_sides(
    task: TableComparisonTask, fact: ComparisonTableFact, column: str,
) -> frozenset[str]:
    """Assert the registry against the native effective frame, including COLUMNS_ADDED.

    Keyless native uses selected minus excluded for COLUMNS_ADDED. Other keyless
    branches use selected; keyed columns additionally must participate in the actual
    compared values. Incompatible/ignored columns never prove identity stability.
    """
    if task.before_descriptor is None or task.current_descriptor is None:
        return frozenset()
    policy = task.policy
    assert policy is not None
    changes = fact.schema_changes
    selected = set(changes.selected_columns)
    excluded = set(policy.compare_excluded_columns)
    incompatible = set(changes.incompatible_columns)
    keyed = bool(changes.effective_compare_key_before or changes.effective_compare_key_current)
    frame = selected - excluded if changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED else selected
    valid = column in frame and column not in incompatible and column not in excluded
    valid = valid and policy.comparison_role == "STANDARD"
    if keyed:
        key = changes.effective_compare_key_before
        valid = (valid and bool(key) and key == changes.effective_compare_key_current
                 and len(set(key)) == len(key) and set(key) <= selected
                 and not (set(key) & (excluded | incompatible)))
    else:
        valid = valid and policy.keyless_policy is KeylessPolicy.FULL_ROW_DIGEST_SET_DIFF
    if valid:
        return frozenset()
    return frozenset(side for side, descriptor in (
        ("BEFORE", task.before_descriptor), ("CURRENT", task.current_descriptor))
        if descriptor is not None and column in {c.name for c in descriptor.columns})


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError("invalid navigation fields")
    return value


def _string(value: object) -> None:
    if type(value) is not str or not value or "\x00" in value:
        raise ValueError("expected a nonempty string")


def validate_navigation(document: object, *, replacement: bool) -> dict[str, Any]:
    doc = _object(document, {"contract_version", "groups", "replacement_sides"})
    if doc["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported navigation version")
    if replacement:
        if doc["groups"] != []:
            raise ValueError("replacement groups must be empty")
        sides = _object(doc["replacement_sides"], {"before", "current"})
        for side in ("before", "current"):
            _groups(sides[side], side.upper(), allow_empty=True)
    else:
        if doc["replacement_sides"] is not None:
            raise ValueError("ordinary navigation forbids replacement_sides")
        _groups(doc["groups"], None)
    return doc


def _groups(value: object, side: str | None, *, allow_empty: bool = False) -> None:
    if type(value) is not list:
        raise ValueError("groups must be an array")
    if allow_empty and value == []:
        return
    if len(value) != len(GROUPS):
        raise ValueError("navigation requires five ordered groups")
    tables: dict[str, tuple[str, bool]] = {}
    item_keys: set[str] = set()
    scopes: dict[str, object] = {}
    for raw, (key, _) in zip(value, GROUPS, strict=True):
        group = _object(raw, {"group_key", "label", "items"})
        if group["group_key"] != key or type(group["items"]) is not list:
            raise ValueError("invalid group order or items")
        _string(group["label"])
        for raw_item in group["items"]:
            item = _object(raw_item, {"item_key", "item_kind", "label", "attributes", "tabs"})
            _string(item["item_key"])
            _string(item["label"])
            if item["item_key"] in item_keys:
                raise ValueError("duplicate item key")
            item_keys.add(item["item_key"])
            if item["item_kind"] not in {"FORWARD_CHANNEL", "DEVICE", "COMPOSITE_SIGNAL_DEVICE", "PROTOCOL_CHANNEL", "TABLE"}:
                raise ValueError("invalid item kind")
            if type(item["attributes"]) is not dict or type(item["tabs"]) is not list:
                raise ValueError("invalid attributes or empty item")
            for attr in item["attributes"].values():
                if type(attr) not in {str, int} or (type(attr) is int and abs(attr) > SAFE_INTEGER):
                    raise ValueError("invalid attribute scalar")
            tabs: set[str] = set()
            for raw_tab in item["tabs"]:
                tab = _object(raw_tab, {"tab_key", "label", "table_id", "row_filter", "facts"})
                for name in ("tab_key", "label", "table_id"):
                    _string(tab[name])
                if tab["tab_key"] in tabs:
                    raise ValueError("duplicate tab key")
                tabs.add(tab["tab_key"])
                filtered = tab["row_filter"] is not None
                previous = tables.get(tab["table_id"])
                if previous is not None and (not filtered or not previous[1] or previous[0] != key):
                    raise ValueError("table claimed twice or mixed whole/filter tabs")
                tables[tab["table_id"]] = (key, filtered)
                if filtered:
                    row_filter = _object(tab["row_filter"], {"before", "current"})
                    if all(v is None for v in row_filter.values()):
                        raise ValueError("empty row filter")
                    for label, predicate in row_filter.items():
                        if side is not None and label.upper() != side and predicate is not None:
                            raise ValueError("replacement filter crosses sides")
                        if predicate is not None:
                            _predicate(predicate)
                if side is not None or not filtered:
                    if tab["facts"] is not None:
                        raise ValueError("whole/replacement tabs forbid local facts")
                else:
                    facts = _object(tab["facts"], {"basis", "change_kind", "risk_level", "before_row_count", "current_row_count", "table_scope"})
                    _facts(facts)
                    if tab["table_id"] in scopes and scopes[tab["table_id"]] != facts["table_scope"]:
                        raise ValueError("table scope must agree across tabs")
                    scopes[tab["table_id"]] = facts["table_scope"]


def _predicate(value: object) -> None:
    pred = _object(value, {"column", "values"})
    _string(pred["column"])
    values = pred["values"]
    if type(values) is not list or not values or type(values[0]) not in {str, int}:
        raise ValueError("invalid predicate values")
    kind = type(values[0])
    if any(type(v) is not kind or (kind is int and abs(v) > SAFE_INTEGER) for v in values):
        raise ValueError("mixed or unsafe predicate")
    if values != sorted(set(values), key=(lambda x: x.encode("utf-8")) if kind is str else None):
        raise ValueError("predicate values must be unique and ordered")


def _facts(facts: dict[str, Any]) -> None:
    levels = {v.value for v in RiskLevel} | {None}
    if facts["basis"] == "EXACT":
        if facts["change_kind"] not in {"UNCHANGED", "ADDED", "DELETED", "UPDATED"}:
            raise ValueError("exact facts need a change kind")
    elif facts["basis"] == "TABLE_FALLBACK":
        if facts["change_kind"] is not None or facts["risk_level"] is not None:
            raise ValueError("fallback facts must remain unknown")
    else:
        raise ValueError("invalid facts basis")
    if facts["risk_level"] not in levels:
        raise ValueError("invalid local risk")
    for name in ("before_row_count", "current_row_count"):
        if facts[name] is not None and (type(facts[name]) is not int or facts[name] < 0):
            raise ValueError("invalid row count")
    if facts["table_scope"] is not None:
        scope = _object(facts["table_scope"], {"change", "risk_level"})
        if type(scope["change"]) is not bool or scope["risk_level"] not in levels:
            raise ValueError("invalid table scope")
        if not scope["change"] and scope["risk_level"] is None:
            raise ValueError("empty table scope must be null")


def navigation_bytes(document: object, *, replacement: bool) -> bytes:
    data = canonicalize_json_value(validate_navigation(document, replacement=replacement))
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("RESOURCE_LIMIT_EXCEEDED")
    return data


_DIAGNOSTIC_PARAMS = {
    "DEVICE_ADDRESS_DUPLICATE": {"dev_addr"},
    "DEVICE_GID_DUPLICATE": {"gid"},
    "DEVICE_TAB_COUNT_UNKNOWN": {"identity_column"},
    "DEVICE_ROWS_UNASSIGNED": {"identity_column", "row_count", "changed_row_count"},
    "CHANNEL_TABLE_UNCLAIMED": {"board", "link_no"},
    "PROTOCOL_EXE_MISSING": {"board", "link_no"},
    "PROTOCOL_TABLE_NOT_FOUND": {"board", "link_no", "protocol", "expected_tables"},
    "APP_TABLE_CFG_MISSING": {"app_name"},
    "APP_TABLE_CFG_DUPLICATE": {"app_name", "table_cfg"},
    "APP_TABLE_NOT_FOUND": {"app_name", "table_cfg"},
    "DEVICE_TAB_FACTS_UNAVAILABLE": {"identity_column", "reason"},
    "DEVICE_FILTER_VALUE_UNSUPPORTED": {"identity_column", "reason"},
}


def validate_diagnostics(
    document: object, navigation: dict[str, Any], table_ids: frozenset[str],
) -> dict[str, Any]:
    """Validate fixed-code params, side/targets and the per-table fallback invariant."""
    doc = _object(document, {"contract_version", "diagnostics"})
    if doc["contract_version"] != CONTRACT_VERSION or type(doc["diagnostics"]) is not list or not doc["diagnostics"]:
        raise ValueError("invalid diagnostics envelope")
    replacement = navigation["replacement_sides"] is not None
    namespaces = navigation["replacement_sides"] if replacement else {"ordinary": navigation["groups"]}
    facts: dict[str, str] = {}
    for groups in namespaces.values():
        for group in groups:
            for item in group["items"]:
                for tab in item["tabs"]:
                    if tab["facts"] is not None:
                        basis = tab["facts"]["basis"]
                        if tab["table_id"] in facts and facts[tab["table_id"]] != basis:
                            raise ValueError("fallback must apply to all table tabs")
                        facts[tab["table_id"]] = basis
    fallback_counts: dict[str, int] = {}
    encoded: list[bytes] = []
    for raw in doc["diagnostics"]:
        diagnostic = _object(raw, {"code", "target", "side", "params"})
        code = diagnostic["code"]
        if type(code) is not str or code not in _DIAGNOSTIC_PARAMS:
            raise ValueError("invalid diagnostic code")
        params = _object(diagnostic["params"], _DIAGNOSTIC_PARAMS[code])
        side = diagnostic["side"]
        if side not in {None, "BEFORE", "CURRENT"} or (replacement and side is None):
            raise ValueError("invalid diagnostic side")
        if code not in {"CHANNEL_TABLE_UNCLAIMED", "DEVICE_TAB_FACTS_UNAVAILABLE"} and side is None:
            raise ValueError("diagnostic requires actual side")
        if code == "DEVICE_TAB_FACTS_UNAVAILABLE" and (replacement or side is not None):
            raise ValueError("local facts diagnostic is ordinary and table-wide")
        for name, value in params.items():
            if name == "expected_tables":
                if type(value) is not list or any(type(v) is not str for v in value):
                    raise ValueError("invalid expected table names")
            elif name in {"board", "link_no", "dev_addr", "gid", "row_count", "changed_row_count"}:
                if not (value is None and name == "changed_row_count") and (type(value) is not int or abs(value) > SAFE_INTEGER):
                    raise ValueError("invalid diagnostic integer")
            elif not (value is None and name == "app_name") and type(value) is not str:
                raise ValueError("invalid diagnostic string")
        if code == "DEVICE_FILTER_VALUE_UNSUPPORTED" and params["reason"] not in {"INTEGER_OUT_OF_RANGE", "UNSUPPORTED_TYPE", "IDENTITY_EXCLUDED"}:
            raise ValueError("invalid unsupported reason")
        if code == "DEVICE_TAB_FACTS_UNAVAILABLE" and params["reason"] not in {"RECORDS_UNAVAILABLE", "RISK_ATTRIBUTION_UNAVAILABLE", "TABLE_DEGRADED"}:
            raise ValueError("invalid fallback reason")
        target = _object(diagnostic["target"], {"group_key", "item_key", "tab_key", "table_id"})
        if target["table_id"] is not None and target["table_id"] not in table_ids:
            raise ValueError("diagnostic references absent table")
        groups = namespaces[side.lower()] if replacement else namespaces["ordinary"]
        group = next((g for g in groups if g["group_key"] == target["group_key"]), None)
        if target["group_key"] is not None and group is None:
            raise ValueError("diagnostic references absent group")
        item = None if group is None else next((i for i in group["items"] if i["item_key"] == target["item_key"]), None)
        if target["item_key"] is not None and item is None:
            raise ValueError("diagnostic references absent item")
        if target["tab_key"] is not None and (item is None or not any(t["tab_key"] == target["tab_key"] for t in item["tabs"])):
            raise ValueError("diagnostic references absent tab")
        if code == "DEVICE_TAB_FACTS_UNAVAILABLE":
            name = target["table_id"]
            fallback_counts[name] = fallback_counts.get(name, 0) + 1
            if target != {"group_key": "SECONDARY_DEVICES", "item_key": None, "tab_key": None, "table_id": name}:
                raise ValueError("invalid local facts diagnostic target")
        encoded.append(canonicalize_json_value(diagnostic))
    if encoded != sorted(set(encoded)):
        raise ValueError("diagnostics must have canonical order without duplicates")
    if {name for name, basis in facts.items() if basis == "TABLE_FALLBACK"} != set(fallback_counts) or any(n != 1 for n in fallback_counts.values()):
        raise ValueError("fallback diagnostics do not match local facts")
    return doc
