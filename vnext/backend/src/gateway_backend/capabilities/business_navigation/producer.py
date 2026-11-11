"""Five-group business navigation. Every shared table side is scanned once.

Only registry/device identities retain counters; orphan identities are aggregated,
so a large unassigned table cannot create a row-sized navigation index.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from contextlib import AbstractContextManager
from typing import Any

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.business_navigation.contracts import (
    CONTRACT_VERSION, GROUPS, SAFE_INTEGER, NavigationRow, NavigationSide,
    NavigationTable, Scalar, navigation_bytes, validate_diagnostics,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RiskAnnotation, RiskLevel, RiskTargetType,
)

POINT_TABLES = (
    ("device_st", "状态类"), ("device_mx", "测量类"), ("device_co", "控制类"),
    ("device_sg", "定值"), ("device_sp", "装置参数"), ("device_cnt", "计量类"),
    ("device_sn", "定值区号"), ("device_tap", "档位"), ("device_other", "其它信息"),
    ("device_disturb", "扰动数据"), ("device_cfg", "装置配置"),
)
FORWARD_TABS = (
    ("syx", "单点遥信"), ("dyx", "双点遥信"), ("yc", "遥测"),
    ("syk", "单点遥控"), ("dyk", "双点遥控"), ("yt", "遥调"),
    ("ym", "遥脉"), ("sc", "顺控"), ("yp", "遥步"),
)
_FORWARD = re.compile(r"^b(\d+)_n(\d+)_(?:iec104_(?:syx|dyx|yc|syk|dyk|yt|ym|sc|yp)_list|sg_cfg)$")
_SEVERITY = {level: rank for rank, level in enumerate((
    RiskLevel.LOW, RiskLevel.MEDIUM_LOW, RiskLevel.UNKNOWN, RiskLevel.MEDIUM_HIGH, RiskLevel.HIGH))}


def maximum_risk(*levels: RiskLevel | None) -> RiskLevel | None:
    return max((v for v in levels if v is not None), key=_SEVERITY.__getitem__, default=None)


def reduce_table_risks(
    table_ids: Iterable[str], events: Iterable[RiskAnnotation],
) -> dict[str, RiskLevel | None]:
    """Consume actual typed TABLE/COMPARISON events, including cache-replayed events.

    Row annotations and mixed RiskReport.table summaries intentionally have no path
    into this reduction. Callers must supply events before publication truncation.
    """
    result: dict[str, RiskLevel | None] = dict.fromkeys(table_ids)
    global_level: RiskLevel | None = None
    for event in events:
        target = event.target
        if target.target_type not in {RiskTargetType.TABLE, RiskTargetType.COMPARISON}:
            continue
        if target.table_name is None:
            if target.target_type is RiskTargetType.COMPARISON:
                global_level = maximum_risk(global_level, event.risk_level)
        elif target.table_name in result:
            result[target.table_name] = maximum_risk(result[target.table_name], event.risk_level)
    return {name: maximum_risk(level, global_level) for name, level in result.items()}


def scalar_reason(sql_type: str | None, value: Scalar) -> str | None:
    """Strict same-side scalar eligibility; string-looking numbers remain strings."""
    if sql_type is None:
        return "UNSUPPORTED_TYPE"
    spelling = sql_type.upper().strip()
    integer = re.fullmatch(r"(TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT)(?:\(\d+\))?( UNSIGNED)?", spelling)
    if integer:
        if value is None:
            return None
        if type(value) is not int:
            raise ValueError("identity value contradicts integer descriptor")
        width = {"TINYINT": 8, "SMALLINT": 16, "MEDIUMINT": 24, "INT": 32, "INTEGER": 32, "BIGINT": 64}[integer[1]]
        unsigned = integer[2] is not None
        low, high = (0, 2**width - 1) if unsigned else (-2**(width - 1), 2**(width - 1) - 1)
        if not low <= value <= high:
            raise ValueError("identity value contradicts declared integer width")
        return "INTEGER_OUT_OF_RANGE" if abs(value) > SAFE_INTEGER else None
    if re.fullmatch(r"(?:CHAR|VARCHAR)(?:\(\d+\))?|TINYTEXT|TEXT|MEDIUMTEXT|LONGTEXT", spelling):
        if value is not None and type(value) is not str:
            raise ValueError("identity value contradicts string descriptor")
        return None
    return "UNSUPPORTED_TYPE"


@dataclass(frozen=True, slots=True)
class NavigationResult:
    document: dict[str, Any]
    diagnostics: dict[str, Any] | None
    scanned_rows: int

    def to_bytes(self) -> bytes:
        return navigation_bytes(self.document, replacement=self.document["replacement_sides"] is not None)


def build_navigation(
    tables: tuple[NavigationTable, ...], *, replacement: bool = False,
    check: Callable[[], None], reserve: Callable[[int], AbstractContextManager[object]],
    max_state_bytes: int = 16 * 1024 * 1024,
) -> NavigationResult:
    """Charge bounded state and serialization buffers to the existing operation M.

    The caller supplies operation.memory.reserve and operation.checkpoint; neither
    a separate memory budget nor an independent cancellation lifetime is created.
    """
    check()
    if type(max_state_bytes) is not int or not 0 < max_state_bytes <= 16 * 1024 * 1024:
        raise ValueError("invalid navigation state bound")
    with reserve(max_state_bytes + 40 * 1024 * 1024):
        return _build_navigation(tables, replacement=replacement, check=check,
                                 max_state_bytes=max_state_bytes)


def _build_navigation(
    tables: tuple[NavigationTable, ...], *, replacement: bool = False,
    check: Callable[[], None], max_state_bytes: int = 16 * 1024 * 1024,
) -> NavigationResult:
    """check shares the operation cancellation/deadline; state has an explicit bound.

    Inputs are owner-verified logical sides. Unchanged pairs may alias the current
    stream for before counting (DC39) only after proving equal content/schema.
    """
    if len({t.table_id for t in tables}) != len(tables) or len({t.table_name for t in tables}) != len(tables):
        raise ValueError("duplicate navigation table")
    builder = _Builder(tables, check, max_state_bytes)
    if replacement:
        sides: dict[str, list[dict[str, Any]]] = {}
        for side in ("BEFORE", "CURRENT"):
            subset = tuple(replace(t,
                before=t.before if side == "BEFORE" else None,
                current=t.current if side == "CURRENT" else None,
                identity_excluded_sides=frozenset(),
            ) for t in tables if (t.before if side == "BEFORE" else t.current) is not None)
            sides[side.lower()] = builder.groups(subset, side) if subset else []
        document: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "groups": [], "replacement_sides": sides}
    else:
        document = {"contract_version": CONTRACT_VERSION,
                    "groups": builder.groups(tables, None), "replacement_sides": None}
    navigation_bytes(document, replacement=replacement)
    diagnostics = sorted({canonicalize_json_value(d) for d in builder.diagnostics})
    import json
    diagnostic_doc = None if not diagnostics else {"contract_version": CONTRACT_VERSION,
        "diagnostics": [json.loads(d) for d in diagnostics]}
    if diagnostic_doc is not None and len(canonicalize_json_value(diagnostic_doc)) > 4 * 1024 * 1024:
        raise ValueError("RESOURCE_LIMIT_EXCEEDED")
    if diagnostic_doc is not None:
        validate_diagnostics(diagnostic_doc, document, frozenset(t.table_id for t in tables))
    return NavigationResult(document, diagnostic_doc, builder.scanned)


class _Builder:
    def __init__(self, tables: tuple[NavigationTable, ...], check: Callable[[], None], limit: int):
        self.check = check
        self.limit = limit
        self.used = 0
        self.scanned = 0
        self.diagnostics: list[dict[str, Any]] = []
        self.names = {t.table_name: t for t in tables}

    def charge(self, value: object) -> None:
        self.check()
        self.used += len(canonicalize_json_value(value)) + 128
        if self.used > self.limit:
            raise ValueError("RESOURCE_LIMIT_EXCEEDED")

    def rows(self, side: NavigationSide | None) -> Iterable[NavigationRow]:
        if side is not None:
            count = 0
            for row in side.rows():
                self.check()
                self.scanned += 1
                count += 1
                yield row
            if count != side.row_count:
                raise ValueError("navigation row count differs from bound descriptor")

    def diagnostic(self, code: str, group: str, *, table: NavigationTable | None = None,
                   item: str | None = None, side: str | None = None, **params: object) -> None:
        value = {"code": code, "side": side, "params": params,
                 "target": {"group_key": group, "item_key": item, "tab_key": None,
                            "table_id": table.table_id if table else None}}
        self.charge(value)
        self.diagnostics.append(value)

    def tab(self, table: NavigationTable, key: str = "table", label: str | None = None) -> dict[str, Any]:
        return {"tab_key": key, "label": label or table.display_name,
                "table_id": table.table_id, "row_filter": None, "facts": None}

    def item(self, key: str, kind: str, label: str, tabs: list[dict[str, Any]],
             **attributes: Scalar) -> dict[str, Any]:
        item = {"item_key": key, "item_kind": kind, "label": label,
                "attributes": attributes, "tabs": tabs}
        self.charge(item)
        return item

    def groups(self, tables: tuple[NavigationTable, ...], side: str | None) -> list[dict[str, Any]]:
        diagnostic_start = len(self.diagnostics)
        names = {t.table_name: t for t in tables}
        groups: list[dict[str, Any]] = [{"group_key": key, "label": label, "items": []} for key, label in GROUPS]
        claimed: set[str] = set()
        channels: dict[tuple[int, int], dict[str, NavigationRow]] = defaultdict(dict)
        qualified: set[tuple[int, int]] = set()
        # One scan of the small registry table per existing logical side.
        net = names.get("net_cfg")
        if net:
            for label, source in (("BEFORE", net.before), ("CURRENT", net.current)):
                for row in self.rows(source):
                    board, link = row.values.get("board"), row.values.get("link_no")
                    if type(board) is not int or type(link) is not int or max(abs(board), abs(link)) > SAFE_INTEGER:
                        continue
                    key = (board, link)
                    existing = channels[key].get(label)
                    if existing is None or row.canonical_order_key < existing.canonical_order_key:
                        if existing is None:
                            self.charge([board, link, label, dict(row.values)])
                        channels[key][label] = row
                    tab_num = row.values.get("tab_num")
                    if str(row.values.get("exe") or "").lower() == "iec104" and type(tab_num) is int and tab_num > 0:
                        qualified.add(key)
        for (board, link), rows in sorted(channels.items()):
            if (board, link) not in qualified:
                continue
            prefix = f"b{board}_n{link}"
            tabs = []
            for suffix, label in (*((f"iec104_{s}_list", label) for s, label in FORWARD_TABS), ("sg_cfg", "定值")):
                table = names.get(f"{prefix}_{suffix}")
                if table is not None:
                    claimed.add(table.table_name)
                    if not self.omittable(table):
                        tabs.append(self.tab(table, suffix, table.display_name if suffix == "sg_cfg" and table.display_name != table.table_name else label))
            if tabs:
                current = rows.get("CURRENT")
                before = rows.get("BEFORE")
                label = self.business_label(current, before, "channel_desc", prefix)
                groups[0]["items"].append(self.item(f"channel:{prefix}", "FORWARD_CHANNEL", label, tabs, board=board, link_no=link))
        self.devices(groups[1]["items"], names, claimed, side)
        if net:
            claimed.add("net_cfg")
            groups[2]["items"].append(self.item("protocol:table", "TABLE", net.display_name, [self.tab(net)]))
        for (board, link), rows in sorted(channels.items()):
            prefix = f"b{board}_n{link}"
            tabs_by_name: dict[str, dict[str, Any]] = {}
            for label, row in rows.items():
                protocol = str(row.values.get("exe") or "").lower()
                if not protocol:
                    self.diagnostic("PROTOCOL_EXE_MISSING", "COMMUNICATION_PROTOCOLS", item=f"protocol:{prefix}", side=label, board=board, link_no=link)
                    continue
                segment = "nr103d" if protocol == "dev103" else protocol
                candidates = [f"{prefix}_{segment}_cfg", f"{prefix}_{segment}_dev_cfg"]
                found = False
                for name in candidates:
                    table = names.get(name)
                    if table is not None and (table.before if label == "BEFORE" else table.current) is not None:
                        found = True
                        if name not in claimed:
                            tabs_by_name[name] = self.tab(table, name)
                if not found:
                    self.diagnostic("PROTOCOL_TABLE_NOT_FOUND", "COMMUNICATION_PROTOCOLS", item=f"protocol:{prefix}", side=label, board=board, link_no=link, protocol=protocol, expected_tables=candidates)
            claimed.update(tabs_by_name)
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "channel_desc", prefix)
            protocol_name = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "protocol_name", "")
            groups[2]["items"].append(self.item(f"protocol:{prefix}", "PROTOCOL_CHANNEL", (label + " " + protocol_name).strip(), list(tabs_by_name.values()), board=board, link_no=link, protocol=self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "exe", "").lower()))
        self.globals(groups[3]["items"], names, claimed)
        for name, table in sorted(names.items()):
            if name in claimed:
                continue
            groups[4]["items"].append(self.item(f"table:{name}", "TABLE", table.display_name, [self.tab(table)]))
            match = _FORWARD.fullmatch(name)
            if match:
                self.diagnostic("CHANNEL_TABLE_UNCLAIMED", "OTHER_TABLES", table=table, item=f"table:{name}", side=side, board=int(match[1]), link_no=int(match[2]))
        # Diagnostics can target an absent protocol item: use the existing net_cfg
        # table item as the nearest visible owner after empty channels are omitted.
        visible = {i["item_key"] for g in groups for i in g["items"]}
        for diagnostic in self.diagnostics[diagnostic_start:]:
            target = diagnostic["target"]
            if target["group_key"] == "COMMUNICATION_PROTOCOLS" and target["item_key"] not in visible:
                target["item_key"] = "protocol:table" if net else None
                target["table_id"] = net.table_id if net else None
        return groups

    @staticmethod
    def business_label(current: NavigationRow | None, before: NavigationRow | None, column: str, default: str) -> str:
        for row in (current, before):
            value = None if row is None else row.values.get(column)
            if isinstance(value, str) and value.strip():
                return value
        return default

    @staticmethod
    def omittable(table: NavigationTable) -> bool:
        return (table.unchanged and not table.table_change and not table.evidence.any_table_risk
                and table.evidence.table_risk is None
                and all(s is None or s.row_count == 0 for s in (table.before, table.current)))

    def globals(self, output: list[dict[str, Any]], names: dict[str, NavigationTable], claimed: set[str]) -> None:
        for name in ("project", "prot_list", "app_cfg"):
            if name in names and name not in claimed:
                table = names[name]
                claimed.add(name)
                output.append(self.item(f"global:{name}", "TABLE", table.display_name, [self.tab(table)]))
        app = names.get("app_cfg")
        if app is None:
            return
        targets: dict[str, dict[str, NavigationRow]] = defaultdict(dict)
        for side, source in (("BEFORE", app.before), ("CURRENT", app.current)):
            seen: set[str] = set()
            for row in self.rows(source):
                target = row.values.get("table_cfg")
                app_name = row.values.get("app_name")
                if not isinstance(target, str) or not target.strip():
                    self.diagnostic("APP_TABLE_CFG_MISSING", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name)
                elif target not in names:
                    self.diagnostic("APP_TABLE_NOT_FOUND", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name, table_cfg=target)
                elif target in seen or target in claimed:
                    if target in seen:
                        existing = targets[target].get(side)
                        if existing is not None and row.canonical_order_key < existing.canonical_order_key:
                            targets[target][side] = row
                    self.diagnostic("APP_TABLE_CFG_DUPLICATE", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name, table_cfg=target)
                else:
                    seen.add(target)
                    existing = targets[target].get(side)
                    if existing is None or row.canonical_order_key < existing.canonical_order_key:
                        self.charge([target, side, dict(row.values)])
                        targets[target][side] = row
        for target, rows in sorted(targets.items()):
            claimed.add(target)
            table = names[target]
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "app_name", table.display_name)
            output.append(self.item(f"global:{target}", "TABLE", label, [self.tab(table)]))

    def devices(self, output: list[dict[str, Any]], names: dict[str, NavigationTable],
                claimed: set[str], replacement_side: str | None) -> None:
        diagnostic_start = len(self.diagnostics)
        device = names.get("device")
        representatives: dict[int, dict[str, NavigationRow]] = defaultdict(dict)
        gids: dict[str, dict[int, set[Scalar]]] = {"BEFORE": defaultdict(set), "CURRENT": defaultdict(set)}
        unsafe_addresses: set[str] = set()
        unsafe_gids: set[str] = set()
        if device is not None:
            claimed.add("device")
            output.append(self.item("device:table", "TABLE", device.display_name, [self.tab(device)]))
            for side, source in (("BEFORE", device.before), ("CURRENT", device.current)):
                address_counts: Counter[int] = Counter()
                gid_counts: Counter[Scalar] = Counter()
                for row in self.rows(source):
                    assert source is not None
                    addr, gid = row.values.get("dev_addr"), row.values.get("gid")
                    reason = scalar_reason(source.column_types.get("dev_addr"), addr)
                    if reason is not None or (addr is not None and type(addr) is not int):
                        unsafe_addresses.add(side)
                        continue
                    if addr is None:
                        continue
                    assert isinstance(addr, int)
                    address_counts[addr] += 1
                    previous = representatives[addr].get(side)
                    if previous is None or row.canonical_order_key < previous.canonical_order_key:
                        self.charge([addr, side, dict(row.values)])
                        representatives[addr][side] = row
                    if scalar_reason(source.column_types.get("gid"), gid) is not None:
                        unsafe_gids.add(side)
                    elif gid is not None:
                        if gid not in gids[side][addr]:
                            self.charge([addr, gid])
                            gids[side][addr].add(gid)
                        gid_counts[gid] += 1
                if side in unsafe_addresses:
                    self.diagnostic("DEVICE_FILTER_VALUE_UNSUPPORTED", "SECONDARY_DEVICES", table=device, item="device:table", side=side, identity_column="dev_addr", reason="INTEGER_OUT_OF_RANGE" if source and scalar_reason(source.column_types.get("dev_addr"), None) is None else "UNSUPPORTED_TYPE")
                for addr, count in address_counts.items():
                    if count > 1:
                        self.diagnostic("DEVICE_ADDRESS_DUPLICATE", "SECONDARY_DEVICES", item=f"device:addr:{addr}" if addr != 65532 else "device:composite", side=side, dev_addr=addr)
                for gid, count in gid_counts.items():
                    if count > 1:
                        self.diagnostic("DEVICE_GID_DUPLICATE", "SECONDARY_DEVICES", table=device, side=side, gid=gid)
        composite = names.get("composite_signal_point")
        if composite is not None:
            representatives.setdefault(65532, {})
        candidates: dict[int, dict[str, Any]] = {}
        for addr, rows in sorted(representatives.items(), key=lambda pair: (pair[0] != 65532, pair[0])):
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "description", f"装置 {addr}")
            current = rows.get("CURRENT") or rows.get("BEFORE")
            attrs: dict[str, Scalar] = {"dev_addr": addr}
            if current is not None:
                gid = current.values.get("gid")
                if type(gid) is int and abs(gid) <= SAFE_INTEGER:
                    attrs["gid"] = gid
            candidates[addr] = {"item_key": "device:composite" if addr == 65532 else f"device:addr:{addr}",
                "item_kind": "COMPOSITE_SIGNAL_DEVICE" if addr == 65532 else "DEVICE",
                "label": label, "attributes": attrs, "tabs": []}
        if composite is not None:
            claimed.add(composite.table_name)
            candidates[65532]["tabs"].append(self.tab(composite))
        whole_items: list[dict[str, Any]] = []
        for name, tab_label in POINT_TABLES:
            table = names.get(name)
            if table is None:
                continue
            claimed.add(name)
            column = "gid" if name == "device_cfg" else "dev_addr"
            predicates: dict[int, dict[str, dict[str, Any] | None]] = {
                addr: {"before": None, "current": None} for addr in candidates}
            counts: dict[str, dict[int, int] | None] = {}
            owners: dict[str, dict[Scalar, set[int]]] = {"BEFORE": defaultdict(set), "CURRENT": defaultdict(set)}
            failures: dict[str, str] = {}
            orphans: dict[str, int] = {}
            reuse_counts = (table.unchanged and table.before is not None and table.current is not None
                            and table.before.column_types.get(column) == table.current.column_types.get(column))
            known_values = set(representatives) if column == "dev_addr" else {
                value for side_gids in gids.values() for values in side_gids.values() for value in values}
            reused_histogram: Counter[Scalar] | None = None
            reused_total = 0
            for side, source in (("BEFORE", table.before), ("CURRENT", table.current)):
                if source is None:
                    counts[side] = {addr: 0 for addr in candidates}
                    continue
                if side in table.identity_excluded_sides and replacement_side is None:
                    failures[side] = "IDENTITY_EXCLUDED"
                elif side in unsafe_addresses or (column == "gid" and side in unsafe_gids):
                    failures[side] = "INTEGER_OUT_OF_RANGE"
                elif column in source.column_types:
                    reason = scalar_reason(source.column_types[column], None)
                    if reason:
                        failures[side] = reason
                missing_column = column not in source.column_types
                for addr, rows in representatives.items():
                    values: set[Scalar] = set()
                    if side in rows:
                        values = gids[side][addr] if column == "gid" else {addr}
                    values.discard(None)
                    if values and side not in failures:
                        ordered = sorted(values, key=lambda v: (0, v) if type(v) is int else (1, str(v).encode("utf-8")))
                        predicates[addr][side.lower()] = {"column": column, "values": ordered}
                        for value in values:
                            owners[side][value].add(addr)
                side_counts = {addr: 0 for addr in candidates}
                orphan = 0
                if reuse_counts and reused_histogram is not None:
                    for value, addresses in owners[side].items():
                        count = reused_histogram.get(value, 0)
                        for addr in addresses:
                            side_counts[addr] += count
                    covered = sum(count for value, count in reused_histogram.items() if value in owners[side])
                    orphan = reused_total - covered
                else:
                    histogram: Counter[Scalar] = Counter()
                    total = 0
                    scan_source = table.current if reuse_counts else source
                    for row in self.rows(scan_source):
                        total += 1
                        value = row.values.get(column)
                        if not missing_column:
                            reason = scalar_reason(source.column_types[column], value)
                            if reason:
                                failures[side] = reason
                        if value in known_values:
                            histogram[value] += 1
                        if value not in owners[side]:
                            orphan += 1
                    for value, addresses in owners[side].items():
                        count = histogram.get(value, 0)
                        for addr in addresses:
                            side_counts[addr] += count
                    if reuse_counts:
                        reused_histogram, reused_total = histogram, total
                counts[side] = None if missing_column else side_counts
                orphans[side] = orphan
            if reuse_counts and failures.get("BEFORE") == "INTEGER_OUT_OF_RANGE":
                failures["CURRENT"] = "INTEGER_OUT_OF_RANGE"
            if failures:
                key = f"table:{name}"
                whole_items.append(self.item(key, "TABLE", table.display_name, [self.tab(table)]))
                for side, reason in failures.items():
                    self.diagnostic("DEVICE_FILTER_VALUE_UNSUPPORTED", "SECONDARY_DEVICES", table=table, item=key, side=side, identity_column=column, reason=reason)
                continue
            reason = table.evidence.fallback_reason() if replacement_side is None else None
            if replacement_side is None and any(
                context is not None and column not in context
                for record in table.evidence.records for context in (record.before, record.current)
            ):
                reason = "RECORDS_UNAVAILABLE"
            changed_values: dict[str, set[Scalar]] = {"BEFORE": set(), "CURRENT": set()}
            risk_values: dict[str, dict[Scalar, RiskLevel | None]] = {"BEFORE": {}, "CURRENT": {}}
            changed_orphans = {"BEFORE": 0, "CURRENT": 0}
            for record in table.evidence.records:
                self.check()
                for side, context in (("BEFORE", record.before), ("CURRENT", record.current)):
                    if context is not None:
                        value = context.get(column)
                        if value not in owners[side]:
                            changed_orphans[side] += 1
                        else:
                            if value not in changed_values[side]:
                                self.charge([side, value])
                            changed_values[side].add(value)
                            risk_values[side][value] = maximum_risk(risk_values[side].get(value), record.risk_level)
            published = False
            scope = None if not table.table_change and table.evidence.table_risk is None else {
                "change": table.table_change, "risk_level": table.evidence.table_risk}
            for addr, candidate in candidates.items():
                row_filter = predicates[addr]
                if row_filter["before"] is None and row_filter["current"] is None:
                    continue
                old = None if counts.get("BEFORE") is None else counts["BEFORE"][addr]  # type: ignore[index]
                new = None if counts.get("CURRENT") is None else counts["CURRENT"][addr]  # type: ignore[index]
                has_change = False
                row_risk: RiskLevel | None = None
                for label, predicate in row_filter.items():
                    if predicate is not None:
                        for value in predicate["values"]:
                            has_change = has_change or value in changed_values[label.upper()]
                            row_risk = maximum_risk(row_risk, risk_values[label.upper()].get(value))
                change = "UNCHANGED" if not has_change else (
                    "ADDED" if old == 0 and new is not None and new > 0 else (
                        "DELETED" if new == 0 and old is not None and old > 0 else "UPDATED"))
                if (replacement_side is None and reason is None and old == new == 0
                        and not has_change and row_risk is None and scope is None
                        and table.unchanged and not table.evidence.any_table_risk):
                    continue
                facts = None if replacement_side is not None else {
                    "basis": "EXACT" if reason is None else "TABLE_FALLBACK",
                    "change_kind": change if reason is None else None,
                    "risk_level": row_risk if reason is None else None,
                    "before_row_count": old, "current_row_count": new, "table_scope": scope}
                tab = {"tab_key": name, "label": tab_label, "table_id": table.table_id,
                       "row_filter": row_filter, "facts": facts}
                self.charge(tab)
                candidate["tabs"].append(tab)
                published = True
            if not published and (not self.omittable(table) or any(orphans.values())):
                whole_items.append(self.item(f"table:{name}", "TABLE", table.display_name, [self.tab(table)]))
            if published and reason:
                self.diagnostic("DEVICE_TAB_FACTS_UNAVAILABLE", "SECONDARY_DEVICES", table=table, identity_column=column, reason=reason)
            if published or not self.omittable(table):
                for side, source in (("BEFORE", table.before), ("CURRENT", table.current)):
                    if source is None:
                        continue
                    if counts[side] is None:
                        self.diagnostic("DEVICE_TAB_COUNT_UNKNOWN", "SECONDARY_DEVICES", table=table, side=side, identity_column=column)
                    elif orphans.get(side, 0):
                        self.diagnostic("DEVICE_ROWS_UNASSIGNED", "SECONDARY_DEVICES", table=table, side=side, identity_column=column,
                            row_count=orphans[side], changed_row_count=(changed_orphans[side] if reason is None and replacement_side is None else None))
        for candidate in candidates.values():
            self.charge(candidate)
            output.append(candidate)
        output.extend(whole_items)
        visible = {item["item_key"] for item in output}
        for diagnostic in self.diagnostics[diagnostic_start:]:
            target = diagnostic["target"]
            if target["group_key"] == "SECONDARY_DEVICES" and target["item_key"] is not None and target["item_key"] not in visible:
                target["item_key"] = "device:table" if device else None
                target["table_id"] = device.table_id if device else None
