"""Five-group business navigation. Every shared table side is scanned once.

Only registry/device identities retain counters; orphan identities are aggregated,
so a large unassigned table cannot create a row-sized navigation index.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from contextlib import AbstractContextManager, ExitStack
from typing import Any

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.business_navigation.contracts import (
    CONTRACT_VERSION, GROUPS, POINT_TABLES, SAFE_INTEGER, NavigationRow, NavigationSide,
    NavigationTable, Scalar, navigation_bytes, validate_diagnostics,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RiskAnnotation, RiskLevel, RiskTargetType,
)

from gateway_backend.capabilities.table_rules import is_ordered_reference_table, parse_channel_table_name

_PROTOCOL_SEGMENTS = {
    "n": {"dev103": ("nr103d",), "ht103": ("nr103ht",),
          "modbusnetdev": ("modbusnet",), "stdmdsnet": ("stdmds",),
          "dll": ("dll3xx", "dll495"), "dev103_9150": ("nrts103",),
          "mach2dev": ("mach2",), "abb103dev": ("abb103",), "cagc": ("agc",)},
    "c": {"stdmdscom": ("stdmds",), "dll": ("dll3xx", "dll495")},
}

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
    _payload: bytes = field(repr=False)

    def to_bytes(self) -> bytes:
        """Return bytes encoded inside the original operation admission."""
        return self._payload


def build_navigation(
    tables: tuple[NavigationTable, ...], *, replacement: bool = False,
    initial_baseline: bool = False,
    check: Callable[[], None], reserve: Callable[[int], AbstractContextManager[object]],
    resources: ExitStack,
    max_state_bytes: int = 16 * 1024 * 1024,
) -> NavigationResult:
    """Charge bounded state and serialization buffers to the existing operation M.

    The caller supplies operation.memory.reserve, operation.resources and
    operation.checkpoint. Successful result/serialization storage stays admitted
    until the existing operation resources close; failures release immediately.
    """
    check()
    if type(max_state_bytes) is not int or not 0 < max_state_bytes <= 16 * 1024 * 1024:
        raise ValueError("invalid navigation state bound")
    with ExitStack() as admission:
        admission.enter_context(reserve(max_state_bytes + 40 * 1024 * 1024))
        result = _build_navigation(tables, replacement=replacement, initial_baseline=initial_baseline, check=check,
                                   max_state_bytes=max_state_bytes)
        resources.callback(admission.pop_all().close)
        return result


def _build_navigation(
    tables: tuple[NavigationTable, ...], *, replacement: bool = False,
    initial_baseline: bool = False,
    check: Callable[[], None], max_state_bytes: int = 16 * 1024 * 1024,
) -> NavigationResult:
    """check shares the operation cancellation/deadline; state has an explicit bound.

    Inputs are owner-verified logical sides. Unchanged pairs may alias the current
    stream for before counting (DC39) only after proving equal content/schema.
    """
    if len({t.table_id for t in tables}) != len(tables) or len({t.table_name for t in tables}) != len(tables):
        raise ValueError("duplicate navigation table")
    if initial_baseline and (replacement or any(t.before is not None for t in tables)):
        raise ValueError("initial baseline requires an empty before side")
    builder = _Builder(tables, check, max_state_bytes, initial_baseline)
    if replacement:
        sides: dict[str, list[dict[str, Any]]] = {}
        for side in ("BEFORE", "CURRENT"):
            subset = tuple(replace(t,
                before=t.before if side == "BEFORE" else None,
                current=t.current if side == "CURRENT" else None,
                identity_excluded_sides=frozenset(),
            ) for t in tables if (t.before if side == "BEFORE" else t.current) is not None)
            sides[side.lower()] = builder.groups(subset, side) if subset else []
        document: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "initial_baseline": initial_baseline, "groups": [], "replacement_sides": sides, "table_notices": [], "device_definition_changes": []}
    else:
        document = {"contract_version": CONTRACT_VERSION, "initial_baseline": initial_baseline,
                    "groups": builder.groups(tables, None), "replacement_sides": None,
                    "table_notices": sorted(builder.notices, key=lambda n: n["table_id"].encode("utf-8")),
                    "device_definition_changes": sorted(builder.device_changes, key=lambda c: c["record_identity"])}
    payload = navigation_bytes(document, replacement=replacement)
    diagnostics = sorted({canonicalize_json_value(d) for d in builder.diagnostics})
    import json
    diagnostic_doc = None if not diagnostics else {"contract_version": CONTRACT_VERSION,
        "diagnostics": [json.loads(d) for d in diagnostics]}
    if diagnostic_doc is not None and len(canonicalize_json_value(diagnostic_doc)) > 4 * 1024 * 1024:
        raise ValueError("RESOURCE_LIMIT_EXCEEDED")
    if diagnostic_doc is not None:
        validate_diagnostics(diagnostic_doc, document, frozenset(t.table_id for t in tables))
    return NavigationResult(document, diagnostic_doc, builder.scanned, payload)


class _Builder:
    def __init__(self, tables: tuple[NavigationTable, ...], check: Callable[[], None], limit: int, initial_baseline: bool):
        self.check = check
        self.limit = limit
        self.initial_baseline = initial_baseline
        self.used = 0
        self.scanned = 0
        self.diagnostics: list[dict[str, Any]] = []
        self.notices: list[dict[str, Any]] = []
        self.device_changes: list[dict[str, Any]] = []
        self.tables_by_id = {t.table_id: t for t in tables}

    def charge(self, value: object) -> None:
        self.check()
        self.used += len(canonicalize_json_value(value)) + 128
        if self.used > self.limit:
            raise ValueError("RESOURCE_LIMIT_EXCEEDED")

    @staticmethod
    def row_size(row: NavigationRow) -> int:
        # Include full canonical ordering bytes even when values is only the small
        # business-field projection. Count backing conservatively if owners alias it.
        return (sys.getsizeof(row) + sys.getsizeof(row.canonical_order_key)
                + sys.getsizeof(row.values)
                + sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in row.values.items()))

    def retain_row(self, row: NavigationRow, previous: NavigationRow | None) -> None:
        self.check()
        self.used += self.row_size(row) - (0 if previous is None else self.row_size(previous))
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

    def empty(self, table: NavigationTable, old: int | None, new: int | None) -> bool:
        return (not self.replacement and not table.structure_changed
                and (table.before is not None or table.current is not None)
                and all(count == 0 for source, count in ((table.before, old), (table.current, new))
                        if source is not None))

    def summarize(self, groups: list[dict[str, Any]]) -> None:
        for group in groups:
            for item in group["items"]:
                kinds: set[str] = set()
                risk: RiskLevel | None = None
                nonempty = 0
                change_complete = risk_complete = True
                for tab in item["tabs"]:
                    if tab["empty"]:
                        continue
                    nonempty += 1
                    table = self.tables_by_id[tab["table_id"]]
                    facts = tab["facts"]
                    if facts is None:
                        kinds.add(table.change_kind.value)
                        risk = maximum_risk(risk, table.risk_level)
                    else:
                        change_complete = change_complete and facts["basis"] == "EXACT" and facts["membership_complete"]
                        risk_complete = risk_complete and facts["risk_complete"]
                        if facts["change_kind"] is not None:
                            kinds.add(facts["change_kind"])
                        risk = maximum_risk(risk, facts["risk_level"])
                item["summary"] = {"change_kinds": sorted(kinds), "risk_level": risk,
                                   "nonempty_tab_count": nonempty,
                                   "change_complete": change_complete, "risk_complete": risk_complete}
                self.charge(item["summary"])
            group["nonempty_item_count"] = sum(i["summary"]["nonempty_tab_count"] > 0 for i in group["items"])

    def tab(self, table: NavigationTable, key: str = "table", label: str | None = None) -> dict[str, Any]:
        return {"tab_key": key, "label": label or table.display_name,
                "table_id": table.table_id, "row_filter": None, "facts": None,
                "empty": self.empty(table, None if table.before is None else table.before.row_count,
                                    None if table.current is None else table.current.row_count)}

    def item(self, key: str, kind: str, label: str, tabs: list[dict[str, Any]],
             **attributes: Scalar) -> dict[str, Any]:
        item = {"item_key": key, "item_kind": kind, "label": label,
                "attributes": attributes, "tabs": tabs}
        self.charge(item)
        return item

    def groups(self, tables: tuple[NavigationTable, ...], side: str | None) -> list[dict[str, Any]]:
        diagnostic_start = len(self.diagnostics)
        self.replacement = side is not None
        names = {t.table_name: t for t in tables}
        groups: list[dict[str, Any]] = [{"group_key": key, "label": label, "items": []} for key, label in GROUPS]
        claimed: set[str] = set()
        channels: dict[tuple[str, int, int], dict[str, NavigationRow]] = defaultdict(dict)
        registries = {"n": names.get("net_cfg"), "c": names.get("com_cfg")}
        com_has_exe = False
        for kind, registry in registries.items():
            if registry is None:
                continue
            number_column = "link_no" if kind == "n" else "com_no"
            for label, source in self.registry_sides(registry):
                for row in self.rows(source):
                    exe = row.values.get("exe")
                    if not isinstance(exe, str) or not exe.strip():
                        continue
                    if kind == "c":
                        com_has_exe = True
                    board, number = row.values.get("board"), row.values.get(number_column)
                    if (type(board) is not int or type(number) is not int
                            or not 0 <= board <= SAFE_INTEGER or not 0 <= number <= SAFE_INTEGER):
                        continue
                    key = (kind, board, number)
                    existing = channels[key].get(label)
                    if existing is None or row.canonical_order_key < existing.canonical_order_key:
                        if existing is None:
                            self.charge([kind, board, number, label])
                        self.retain_row(row, existing)
                        channels[key][label] = row

        def ordered_keys() -> list[tuple[str, int, int]]:
            return sorted(channels, key=lambda key: (key[0] != "n", key[1], key[2]))

        def prefix(key: tuple[str, int, int]) -> str:
            kind, board, number = key
            return f"b{board}_{kind}{number}"

        def attrs(key: tuple[str, int, int]) -> dict[str, Scalar]:
            kind, board, number = key
            return {"board": board, "link_no" if kind == "n" else "com_no": number}

        def selected_comment(table: NavigationTable) -> str | None:
            source = table.current or table.before
            return None if source is None else source.table_comment

        parsed = {name: parse_channel_table_name(name) for name in names}
        by_channel: dict[tuple[str, int, int], list[str]] = defaultdict(list)
        for name, info in parsed.items():
            if info is not None:
                self.charge([name, info.kind, info.board, info.channel_no])
                by_channel[(info.kind, info.board, info.channel_no)].append(name)
        ordered = {name for name, table in names.items()
                   if is_ordered_reference_table(name, selected_comment(table))}
        forward_tabs: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
        for name in sorted(ordered, key=lambda value: value.encode("utf-8")):
            table = names[name]
            info = parsed[name]
            assert info is not None
            key = (info.kind, info.board, info.channel_no)
            owners = channels.get(key, {})
            actual_owners = [label for label, source in (("CURRENT", table.current), ("BEFORE", table.before))
                             if source is not None and label in owners]
            if actual_owners:
                comment = selected_comment(table) or ""
                tab_label = comment.replace("引用表", "").strip() or name
                forward_tabs[key].append(self.tab(table, name, tab_label))
                claimed.add(name)
            for label, source in (("BEFORE", table.before), ("CURRENT", table.current)):
                if source is not None and label not in owners:
                    group = "FORWARD_CHANNELS" if actual_owners else "OTHER_TABLES"
                    item = f"channel:{prefix(key)}" if actual_owners else f"table:{name}"
                    self.diagnostic("CHANNEL_TABLE_UNCLAIMED", group, table=table,
                        item=item, side=label, channel_prefix=prefix(key),
                        registry_table="net_cfg" if info.kind == "n" else "com_cfg")
        for key in ordered_keys():
            if not forward_tabs[key]:
                continue
            rows = channels[key]
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "channel_desc", prefix(key))
            groups[0]["items"].append(self.item(f"channel:{prefix(key)}", "FORWARD_CHANNEL", label,
                                                forward_tabs[key], **attrs(key)))
        self.devices(groups[1]["items"], names, claimed, side)
        net = registries["n"]
        for kind in ("n", "c"):
            registry = registries[kind]
            if registry is None or (kind == "c" and not com_has_exe):
                continue
            claimed.add(registry.table_name)
            label = next((source.table_comment for source in (registry.current, registry.before)
                          if source is not None and source.table_comment), registry.table_name)
            item_key = "protocol:table" if kind == "n" else "protocol:com_cfg"
            groups[2]["items"].append(self.item(item_key, "TABLE", label, [self.tab(registry, label=label)]))
        for key in ordered_keys():
            kind, _, _ = key
            rows = channels[key]
            tabs_by_name: dict[str, dict[str, Any]] = {}
            for label, row in rows.items():
                exe = row.values["exe"]
                assert isinstance(exe, str)
                protocol = exe.strip().casefold()
                segments = _PROTOCOL_SEGMENTS[kind].get(protocol, (protocol,))
                expected = [f"{prefix(key)}_{segment}" for segment in segments]
                found = False
                for name in sorted(by_channel.get(key, ()), key=lambda value: value.encode("utf-8")):
                    self.check()
                    table, info = names[name], parsed[name]
                    if (info is None or name in ordered or (info.kind, info.board, info.channel_no) != key
                            or not info.suffix.casefold().startswith(segments)
                            or (table.before if label == "BEFORE" else table.current) is None):
                        continue
                    found = True
                    if name not in claimed:
                        tabs_by_name[name] = self.tab(table, name, selected_comment(table) or name)
                if not found:
                    self.diagnostic("PROTOCOL_TABLE_NOT_FOUND", "COMMUNICATION_PROTOCOLS",
                        item=f"protocol:{prefix(key)}", side=label, channel_prefix=prefix(key),
                        registry_table="net_cfg" if kind == "n" else "com_cfg",
                        protocol=protocol, expected_prefixes=expected)
            claimed.update(tabs_by_name)
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "channel_desc", prefix(key))
            protocol_name = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "protocol_name", "")
            exe = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "exe", "").strip().casefold()
            tabs = [tabs_by_name[name] for name in sorted(tabs_by_name, key=lambda value: value.encode("utf-8"))]
            groups[2]["items"].append(self.item(f"protocol:{prefix(key)}", "PROTOCOL_CHANNEL",
                (label + " " + protocol_name).strip(), tabs, **attrs(key), protocol=exe))
        self.globals(groups[3]["items"], names, claimed,
                     ordered | ({"com_cfg"} if not com_has_exe else set()))
        for name, table in sorted(names.items()):
            if name not in claimed:
                groups[4]["items"].append(self.item(f"table:{name}", "TABLE", table.display_name, [self.tab(table)]))
        # Diagnostics can target an absent protocol item: use the existing net_cfg
        # table item as the nearest visible owner after empty channels are omitted.
        visible = {i["item_key"] for g in groups for i in g["items"]}
        for diagnostic in self.diagnostics[diagnostic_start:]:
            target = diagnostic["target"]
            if target["group_key"] == "COMMUNICATION_PROTOCOLS" and target["item_key"] not in visible:
                target["item_key"] = "protocol:table" if net else None
                target["table_id"] = net.table_id if net else None
        self.summarize(groups)
        return groups

    @staticmethod
    def registry_sides(table: NavigationTable) -> tuple[tuple[str, NavigationSide | None], ...]:
        before = table.current if table.unchanged and table.before is not None and table.current is not None else table.before
        return (("BEFORE", before), ("CURRENT", table.current))

    @staticmethod
    def business_label(current: NavigationRow | None, before: NavigationRow | None, column: str, default: str) -> str:
        for row in (current, before):
            value = None if row is None else row.values.get(column)
            if column == "app_name" and type(value) is int:
                value = str(value)
            if isinstance(value, str) and value.strip():
                return value
        return default

    def globals(self, output: list[dict[str, Any]], names: dict[str, NavigationTable],
                claimed: set[str], reserved: set[str]) -> None:
        for name in ("project", "prot_list", "app_cfg"):
            if name in names and name not in claimed:
                table = names[name]
                claimed.add(name)
                output.append(self.item(f"global:{name}", "TABLE", table.display_name, [self.tab(table)]))
        app = names.get("app_cfg")
        if app is None:
            return
        targets: dict[str, dict[str, NavigationRow]] = defaultdict(dict)
        for side, source in self.registry_sides(app):
            seen: set[str] = set()
            for row in self.rows(source):
                target = row.values.get("table_cfg")
                raw_name = row.values.get("app_name")
                app_name = str(raw_name) if type(raw_name) is int else (raw_name if isinstance(raw_name, str) else None)
                # Disabled modules may legitimately omit their optional parameter table.
                # Keep any existing target browsable, but do not warn for its absence.
                disabled = row.values.get("enable") == "0:NO"
                if not isinstance(target, str) or not target.strip():
                    if disabled:
                        continue
                    self.diagnostic("APP_TABLE_CFG_MISSING", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name)
                elif target not in names or (names[target].before if side == "BEFORE" else names[target].current) is None:
                    if disabled:
                        continue
                    self.diagnostic("APP_TABLE_NOT_FOUND", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name, table_cfg=target)
                elif target in seen or target in claimed or target in reserved:
                    if target in seen:
                        existing = targets[target].get(side)
                        if existing is not None and row.canonical_order_key < existing.canonical_order_key:
                            self.retain_row(row, existing)
                            targets[target][side] = row
                    self.diagnostic("APP_TABLE_CFG_DUPLICATE", "GLOBAL_PARAMETERS", table=app, item="global:app_cfg", side=side, app_name=app_name, table_cfg=target)
                else:
                    seen.add(target)
                    existing = targets[target].get(side)
                    if existing is None or row.canonical_order_key < existing.canonical_order_key:
                        if existing is None:
                            self.charge([target, side])
                        self.retain_row(row, existing)
                        targets[target][side] = row
        for target, rows in sorted(targets.items()):
            claimed.add(target)
            table = names[target]
            label = self.business_label(rows.get("CURRENT"), rows.get("BEFORE"), "app_name", table.display_name)
            output.append(self.item(f"global:{target}", "TABLE", label, [self.tab(table)]))

    def notice(self, table: NavigationTable, scope: dict[str, Any] | None,
               risk: RiskLevel | None, reasons: set[str]) -> None:
        unlocated = None
        if risk is not None or not table.evidence.risk_attribution_complete:
            unlocated = {"risk_level": risk, "count": table.evidence.unlocated_count,
                         "reason_codes": sorted(reasons)}
        if scope is not None or unlocated is not None:
            notice = {"table_id": table.table_id, "table_scope": scope,
                      "unlocated_row_risk": unlocated, "risk_complete": table.evidence.risk_attribution_complete}
            self.charge(notice)
            self.notices.append(notice)

    def devices(self, output: list[dict[str, Any]], names: dict[str, NavigationTable],
                claimed: set[str], replacement_side: str | None) -> None:
        diagnostic_start = len(self.diagnostics)
        device = names.get("device")
        representatives: dict[int, dict[str, NavigationRow]] = defaultdict(dict)
        gids: dict[str, dict[int, set[Scalar]]] = {"BEFORE": defaultdict(set), "CURRENT": defaultdict(set)}
        unsafe_addresses: set[str] = set()
        unsafe_gids: set[str] = set()
        ambiguous_addresses: set[int] = set()
        ambiguous_gids: set[Scalar] = set()
        if device is not None:
            claimed.add("device")
            output.append(self.item("device:table", "TABLE", device.display_name, [self.tab(device)]))
            for side, source in self.registry_sides(device):
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
                        if previous is None:
                            self.charge([addr, side])
                        self.retain_row(row, previous)
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
                        if side == "CURRENT":
                            ambiguous_addresses.add(addr)
                        self.diagnostic("DEVICE_ADDRESS_DUPLICATE", "SECONDARY_DEVICES", item=f"device:addr:{addr}" if addr != 65532 else "device:composite", side=side, dev_addr=addr)
                for gid, count in gid_counts.items():
                    if count > 1:
                        if side == "CURRENT":
                            ambiguous_gids.add(gid)
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
            candidate: dict[str, Any] = {"item_key": "device:composite" if addr == 65532 else f"device:addr:{addr}",
                "item_kind": "COMPOSITE_SIGNAL_DEVICE" if addr == 65532 else "DEVICE",
                "label": label, "attributes": attrs, "tabs": []}
            # Admit the parent before retaining it. Filtered and composite tabs
            # are charged as they are appended, so never count them twice.
            self.charge(candidate)
            candidates[addr] = candidate
        if device is not None and replacement_side is None:
            for record in device.evidence.records:
                device_addresses = []
                keys = []
                for side, device_values in (("BEFORE", record.before), ("CURRENT", record.current)):
                    address = None if device_values is None else device_values.get("dev_addr")
                    if type(address) is not int or abs(address) > SAFE_INTEGER:
                        address = None
                    device_addresses.append(address)
                    keys.append(candidates[address]["item_key"] if address in candidates and side in representatives[address] else None)
                device_change = {"record_identity": record.row_identity,
                    "change_kind": {"ROW_ADDED": "ADDED", "ROW_DELETED": "DELETED", "ROW_MODIFIED": "UPDATED"}[record.kind],
                    "before_item_key": keys[0], "current_item_key": keys[1],
                    "before_dev_addr": device_addresses[0], "current_dev_addr": device_addresses[1],
                    "risk_level": record.risk_level, "risk_complete": device.evidence.risk_attribution_complete}
                self.charge(device_change)
                self.device_changes.append(device_change)
        if composite is not None:
            claimed.add(composite.table_name)
            composite_tab = self.tab(composite)
            self.charge(composite_tab)
            candidates[65532]["tabs"].append(composite_tab)
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
            reused_histogram: Counter[Scalar] | None = None
            reused_total = 0
            histograms: dict[str, Counter[Scalar]] = {}
            for side, source in (("BEFORE", table.before), ("CURRENT", table.current)):
                if source is None:
                    counts[side] = {addr: 0 for addr in candidates}
                    histograms[side] = Counter()
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
                    elif addr == 65532 and column == "dev_addr":
                        # The composite device is virtual; it does not require a
                        # physical device row and never invents a device_cfg gid.
                        values = {65532}
                    values.discard(None)
                    if not missing_column and side not in failures:
                        for value in values:
                            try:
                                value_reason = scalar_reason(source.column_types[column], value)
                            except ValueError:
                                # Both tables may be individually valid but their
                                # registry/target identity categories disagree.
                                value_reason = "UNSUPPORTED_TYPE"
                            if value_reason is not None:
                                failures[side] = value_reason
                                break
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
                    for value in reused_histogram:
                        self.charge([side, value])
                    histograms[side] = reused_histogram.copy()
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
                                # This table will use the whole-table fallback. Do not
                                # retain an unsupported scalar in JSON-charged state.
                                continue
                        if value not in histogram:
                            self.charge([side, value])
                        histogram[value] += 1
                        if value not in owners[side]:
                            orphan += 1
                    for value, addresses in owners[side].items():
                        count = histogram.get(value, 0)
                        for addr in addresses:
                            side_counts[addr] += count
                    histograms[side] = histogram
                    if reuse_counts:
                        reused_histogram, reused_total = histogram, total
                counts[side] = None if missing_column else side_counts
                orphans[side] = orphan
            if reuse_counts and failures.get("BEFORE") == "INTEGER_OUT_OF_RANGE":
                failures["CURRENT"] = "INTEGER_OUT_OF_RANGE"
            if failures:
                if replacement_side is None:
                    unresolved = table.evidence.unlocated_risk
                    reasons = set(table.evidence.unlocated_reasons)
                    for record in table.evidence.records:
                        unresolved = maximum_risk(unresolved, record.risk_level)
                        reasons.update(record.risk_reasons)
                    scope = None if not table.table_change and table.evidence.table_risk is None else {
                        "change": table.table_change, "risk_level": table.evidence.table_risk}
                    self.notice(table, scope, unresolved, reasons)
                key = f"table:{name}"
                whole_items.append(self.item(key, "TABLE", table.display_name, [self.tab(table)]))
                for side, reason in failures.items():
                    self.diagnostic("DEVICE_FILTER_VALUE_UNSUPPORTED", "SECONDARY_DEVICES", table=table, item=key, side=side, identity_column=column, reason=reason)
                continue
            reason = table.local_fallback_reason if replacement_side is None else None
            changed_values: dict[str, set[Scalar]] = {"BEFORE": set(), "CURRENT": set()}
            risk_values: dict[str, dict[Scalar, RiskLevel | None]] = {"BEFORE": {}, "CURRENT": {}}
            changed_orphans = {"BEFORE": 0, "CURRENT": 0}
            record_counts: dict[int, dict[str, int]] = {}
            orphan_risk = table.evidence.unlocated_risk
            orphan_reasons = set(table.evidence.unlocated_reasons)
            for record in table.evidence.records:
                self.check()
                old_owners = set() if record.before is None else owners["BEFORE"].get(record.before.get(column), set())
                new_owners = set() if record.current is None else owners["CURRENT"].get(record.current.get(column), set())
                for address in old_owners | new_owners:
                    if address not in record_counts:
                        self.charge([address, "row_counts"])
                        record_counts[address] = {"added": 0, "deleted": 0, "modified": 0, "moved_in": 0, "moved_out": 0}
                    counts_ = record_counts[address]
                    count_key = {"ROW_ADDED": "added", "ROW_DELETED": "deleted", "ROW_MODIFIED": "modified"}[record.kind]
                    counts_[count_key] += 1
                    if record.kind == "ROW_MODIFIED":
                        counts_["moved_in"] += int(address in new_owners and address not in old_owners)
                        counts_["moved_out"] += int(address in old_owners and address not in new_owners)
                if record.risk_level is not None and not any(
                    values is not None and bool(owners[side].get(values.get(column)))
                    for side, values in (("BEFORE", record.before), ("CURRENT", record.current))
                ):
                    orphan_risk = maximum_risk(orphan_risk, record.risk_level)
                    orphan_reasons.update(record.risk_reasons)
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
            membership_complete = table.may_reuse_unrecorded_identity and reason is None
            for side, histogram in histograms.items():
                for value in histogram:
                    self.charge([side, value])
            remaining = {side: histogram.copy() for side, histogram in histograms.items()}
            if membership_complete:
                for record in table.evidence.records:
                    for side, record_values in (("BEFORE", record.before), ("CURRENT", record.current)):
                        if record_values is not None:
                            value = record_values.get(column)
                            remaining[side][value] -= 1
                membership_complete = (all(n >= 0 for counts_ in remaining.values() for n in counts_.values())
                    and +remaining["BEFORE"] == +remaining["CURRENT"])
            membership: set[int] = set()
            if membership_complete:
                for value, count in remaining["CURRENT"].items():
                    if count > 0 and owners["BEFORE"].get(value, set()) != owners["CURRENT"].get(value, set()):
                        membership.update(owners["BEFORE"].get(value, set()) ^ owners["CURRENT"].get(value, set()))
            published = False
            membership_unknown = False
            scope = None if not table.table_change and table.evidence.table_risk is None else {
                "change": table.table_change, "risk_level": table.evidence.table_risk}
            for addr, candidate in candidates.items():
                row_filter = predicates[addr]
                if row_filter["before"] is None and row_filter["current"] is None:
                    continue
                old = None if counts.get("BEFORE") is None else counts["BEFORE"][addr]  # type: ignore[index]
                new = None if counts.get("CURRENT") is None else counts["CURRENT"][addr]  # type: ignore[index]
                has_change = addr in membership
                row_changes = record_counts.get(addr, {"added": 0, "deleted": 0, "modified": 0, "moved_in": 0, "moved_out": 0})
                row_risk: RiskLevel | None = None
                for label, predicate in row_filter.items():
                    if predicate is not None:
                        for value in predicate["values"]:
                            has_change = has_change or value in changed_values[label.upper()]
                            row_risk = maximum_risk(row_risk, risk_values[label.upper()].get(value))
                change = "UNCHANGED" if not has_change else (
                    "ADDED" if old == 0 and new is not None and new > 0 else (
                        "DELETED" if new == 0 and old is not None and old > 0 else "UPDATED"))
                initial_membership = (self.initial_baseline and not membership_complete and reason is None
                    and table.before is None and table.current is not None
                    and not table.evidence.records
                    and column in table.current.column_types and not table.identity_excluded_sides
                    and addr not in ambiguous_addresses
                    and (column != "gid" or not (gids["CURRENT"][addr] & ambiguous_gids)))
                membership_unknown = membership_unknown or (not membership_complete and not initial_membership)
                facts = None if replacement_side is not None else {
                    "basis": "EXACT" if reason is None else "TABLE_FALLBACK",
                    "change_kind": change if reason is None else None,
                    "risk_level": row_risk, "risk_complete": table.evidence.risk_attribution_complete,
                    "membership_changed": addr in membership, "membership_complete": membership_complete,
                    "membership_initial_baseline": initial_membership,
                    "row_changes": row_changes if reason is None else None,
                    "before_row_count": old, "current_row_count": new, "table_scope": scope}
                tab = {"tab_key": name, "label": tab_label, "table_id": table.table_id,
                       "row_filter": row_filter, "facts": facts, "empty": self.empty(table, old, new)}
                self.charge(tab)
                candidate["tabs"].append(tab)
                published = True
            if not published:
                whole_items.append(self.item(f"table:{name}", "TABLE", table.display_name, [self.tab(table)]))
            if replacement_side is None:
                self.notice(table, scope, orphan_risk, orphan_reasons)
            if published and replacement_side is None and not table.evidence.risk_attribution_complete:
                self.diagnostic("DEVICE_TAB_RISK_UNAVAILABLE", "SECONDARY_DEVICES", table=table, identity_column=column, reason="RISK_ATTRIBUTION_UNAVAILABLE")
            if published and replacement_side is None and membership_unknown:
                self.diagnostic("DEVICE_MEMBERSHIP_UNAVAILABLE", "SECONDARY_DEVICES", table=table, identity_column=column, reason="MEMBERSHIP_UNAVAILABLE")
            if published and reason:
                self.diagnostic("DEVICE_TAB_FACTS_UNAVAILABLE", "SECONDARY_DEVICES", table=table, identity_column=column, reason=reason)
            for side, source in (("BEFORE", table.before), ("CURRENT", table.current)):
                if source is None:
                    continue
                if counts[side] is None:
                    self.diagnostic("DEVICE_TAB_COUNT_UNKNOWN", "SECONDARY_DEVICES", table=table, side=side, identity_column=column)
                elif orphans.get(side, 0):
                    self.diagnostic("DEVICE_ROWS_UNASSIGNED", "SECONDARY_DEVICES", table=table, side=side, identity_column=column,
                        row_count=orphans[side], changed_row_count=(changed_orphans[side] if reason is None and replacement_side is None else None))
        for candidate in candidates.values():
            output.append(candidate)
        output.extend(whole_items)
        visible = {item["item_key"] for item in output}
        for diagnostic in self.diagnostics[diagnostic_start:]:
            target = diagnostic["target"]
            if target["group_key"] == "SECONDARY_DEVICES" and target["item_key"] is not None and target["item_key"] not in visible:
                target["item_key"] = "device:table" if device else None
                target["table_id"] = device.table_id if device else None
