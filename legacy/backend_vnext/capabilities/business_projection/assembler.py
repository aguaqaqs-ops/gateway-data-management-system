from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from .models import (
    BusinessProjectionArtifact,
    BusinessProjectionInput,
    BusinessProjectionKind,
    BusinessProjectionResult,
    BusinessProjectionTable,
)
from .versions import (
    COMMUNICATION_PROTOCOL_PROJECTION_VERSION,
    FORWARD_CHANNEL_PROJECTION_VERSION,
    GLOBAL_PARAMETER_PROJECTION_VERSION,
    SECONDARY_DEVICE_PROJECTION_VERSION,
    UNPARSED_TABLE_PROJECTION_VERSION,
)


_FORWARD_TAB_LABELS: Mapping[str, str] = {
    "iec104_syx_list": "单点遥信",
    "iec104_dyx_list": "双点遥信",
    "iec104_yc_list": "遥测",
    "iec104_syk_list": "单点遥控",
    "iec104_dyk_list": "双点遥控",
    "iec104_yt_list": "遥调",
    "iec104_ym_list": "遥脉",
    "iec104_sc_list": "顺控",
    "iec104_yp_list": "遥步",
}
_SECONDARY_DEVICE_TAB_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("device_st", "状态类", "dev_addr", "dev_addr"),
    ("device_mx", "测量类", "dev_addr", "dev_addr"),
    ("device_co", "控制类", "dev_addr", "dev_addr"),
    ("device_sg", "定值", "dev_addr", "dev_addr"),
    ("device_sp", "装置参数", "dev_addr", "dev_addr"),
    ("device_cnt", "计量类", "dev_addr", "dev_addr"),
    ("device_sn", "定值区号", "dev_addr", "dev_addr"),
    ("device_tap", "档位", "dev_addr", "dev_addr"),
    ("device_other", "其它信息", "dev_addr", "dev_addr"),
    ("device_disturb", "扰动数据", "dev_addr", "dev_addr"),
    ("device_cfg", "装置配置", "gid", "gid"),
)
_PROTOCOL_TABLE_SEGMENT_ALIASES = {"dev103": "nr103d"}
_SECONDARY_DEVICE_METADATA_LABEL_FALLBACK = "装置总表"
_PROTOCOL_METADATA_LABEL_FALLBACK = "网口配置表"
_GLOBAL_FIXED_TABLES: tuple[tuple[str, str], ...] = (
    ("project", "工程参数"),
    ("prot_list", "规约配置"),
)
_APP_CFG_TABLE = "app_cfg"
_APP_CFG_LABEL_FALLBACK = "高级应用"


@dataclass(frozen=True, slots=True)
class _ProjectionContext:
    before_tables: Mapping[str, BusinessProjectionTable]
    current_tables: Mapping[str, BusinessProjectionTable]
    visible_table_names: frozenset[str]

    @property
    def all_table_names(self) -> set[str]:
        return set(self.before_tables) | set(self.current_tables)

    def table(self, table_name: str) -> BusinessProjectionTable | None:
        canonical = canonical_identifier(table_name)
        return self.current_tables.get(canonical) or self.before_tables.get(canonical)

    def table_rows(self, table_name: str, *, side: str) -> tuple[Mapping[str, object], ...]:
        canonical = canonical_identifier(table_name)
        table = self.current_tables.get(canonical) if side == "current" else self.before_tables.get(canonical)
        return () if table is None else table.rows

    def table_rows_loaded(self, table_name: str, *, side: str) -> bool:
        canonical = canonical_identifier(table_name)
        table = self.current_tables.get(canonical) if side == "current" else self.before_tables.get(canonical)
        return False if table is None else table.rows_loaded

    def table_present(self, table_name: str, *, side: str) -> bool:
        canonical = canonical_identifier(table_name)
        tables = self.current_tables if side == "current" else self.before_tables
        return canonical in tables

    def is_visible(self, table_name: str) -> bool:
        return canonical_identifier(table_name) in self.visible_table_names

    def table_exists(self, table_name: str) -> bool:
        return canonical_identifier(table_name) in self.all_table_names


class BusinessProjectionAssembler:
    def assemble(self, request: BusinessProjectionInput) -> BusinessProjectionResult:
        context = _context_from_request(request)
        diagnostics: list[DiagnosticRecord] = []
        consumed: set[str] = set()

        forward_payload, forward_consumed = _build_forward_projection(context)
        consumed.update(forward_consumed)
        secondary_payload, secondary_consumed, secondary_diagnostics = _build_secondary_projection(context)
        consumed.update(secondary_consumed)
        diagnostics.extend(secondary_diagnostics)
        protocol_payload, protocol_consumed, protocol_diagnostics = _build_protocol_projection(context)
        consumed.update(protocol_consumed)
        diagnostics.extend(protocol_diagnostics)
        global_payload, global_consumed, global_diagnostics = _build_global_projection(context)
        consumed.update(global_consumed)
        diagnostics.extend(global_diagnostics)
        unparsed_payload = _build_unparsed_projection(context, consumed)

        projection_payloads = (
            (BusinessProjectionKind.FORWARD_CHANNELS, "forward-channels", forward_payload),
            (BusinessProjectionKind.SECONDARY_DEVICES, "secondary-devices", secondary_payload),
            (BusinessProjectionKind.COMMUNICATION_PROTOCOLS, "communication-protocols", protocol_payload),
            (BusinessProjectionKind.GLOBAL_PARAMETERS, "global-parameters", global_payload),
            (BusinessProjectionKind.UNPARSED_TABLES, "unparsed-tables", unparsed_payload),
        )
        projections = tuple(
            BusinessProjectionArtifact(
                projection_kind=kind,
                projection_id=projection_id,
                payload=payload,
            )
            for kind, projection_id, payload in projection_payloads
        )
        result_diagnostics = tuple(diagnostics)
        if result_diagnostics:
            result_diagnostics = result_diagnostics + (
                DiagnosticRecord(
                    code="PROJECTION_PARTIAL",
                    message="Business projection completed with diagnostics.",
                    phase="business_projection",
                    severity="WARNING",
                    details={"diagnostic_count": len(result_diagnostics)},
                ),
            )
        return BusinessProjectionResult(
            projections=projections,
            consumed_table_names=tuple(sorted(consumed)),
            diagnostics=result_diagnostics,
            summary={
                "projection_count": len(projections),
                "diagnostics_count": len(result_diagnostics),
                "consumed_table_count": len(consumed),
            },
        )


def _context_from_request(request: BusinessProjectionInput) -> _ProjectionContext:
    before_tables = {table.table_name: table for table in request.before_tables}
    current_tables = {table.table_name: table for table in request.current_tables}
    visible_table_names = (
        frozenset(request.surface_table_names)
        if request.surface_table_names
        else frozenset(set(before_tables) | set(current_tables))
    )
    return _ProjectionContext(
        before_tables=before_tables,
        current_tables=current_tables,
        visible_table_names=visible_table_names,
    )


def _base_payload(schema_version: str, projection_kind: BusinessProjectionKind, items: list[dict[str, object]], diagnostics: list[DiagnosticRecord] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "projection_kind": projection_kind.value,
        "items": items,
        "summary": {"item_count": len(items)},
    }
    if diagnostics:
        payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in diagnostics]
    return payload


def _build_forward_projection(context: _ProjectionContext) -> tuple[dict[str, object], set[str]]:
    combined_order, before_rows, current_rows = _combined_net_cfg_rows(context)
    items: list[dict[str, object]] = []
    consumed: set[str] = set()
    for stable_key in combined_order:
        before_row = before_rows.get(stable_key)
        current_row = current_rows.get(stable_key)
        selected_row = current_row or before_row
        protocol_key = _forward_protocol_key(selected_row) or _forward_protocol_key(before_row)
        if protocol_key != "iec104":
            continue
        board, link_no = _parse_channel_key(stable_key)
        tabs: list[dict[str, object]] = []
        for family_key, label in _FORWARD_TAB_LABELS.items():
            table_name = f"{stable_key}_{family_key}"
            if not context.is_visible(table_name):
                continue
            tabs.append(_tab_payload(table_name, label))
        if not tabs:
            continue
        items.append(
            {
                "channel_key": stable_key,
                "board": board,
                "link_no": link_no,
                "protocol": protocol_key,
                "label": _coerce_str(_row_value(current_row, "channel_desc"))
                or _coerce_str(_row_value(before_row, "channel_desc"))
                or stable_key,
                "tabs": tabs,
            }
        )
        consumed.update(str(tab["table_name"]) for tab in tabs)
    if items and context.is_visible("net_cfg"):
        consumed.add("net_cfg")
    return _base_payload(FORWARD_CHANNEL_PROJECTION_VERSION, BusinessProjectionKind.FORWARD_CHANNELS, items), consumed


def _build_protocol_projection(context: _ProjectionContext) -> tuple[dict[str, object], set[str], list[DiagnosticRecord]]:
    combined_order, before_rows, current_rows = _combined_net_cfg_rows(context)
    items: list[dict[str, object]] = []
    consumed: set[str] = set()
    diagnostics: list[DiagnosticRecord] = []
    if context.is_visible("net_cfg") and context.table_exists("net_cfg"):
        consumed.add("net_cfg")
        table = context.table("net_cfg")
        label = _display_name(table, _PROTOCOL_METADATA_LABEL_FALLBACK)
        items.append(
            {
                "protocol_key": "metadata:net_cfg",
                "table_id": "net_cfg",
                "table_name": "net_cfg",
                "label": label,
                "tabs": [_tab_payload("net_cfg", label)],
            }
        )
    for stable_key in combined_order:
        before_row = before_rows.get(stable_key)
        current_row = current_rows.get(stable_key)
        candidates = _protocol_candidates(stable_key, before_row=before_row, current_row=current_row)
        tabs: list[dict[str, object]] = []
        seen: set[str] = set()
        for table_name in candidates:
            if table_name in seen:
                continue
            seen.add(table_name)
            if context.is_visible(table_name):
                tabs.append(_tab_payload(table_name, _display_name(context.table(table_name), table_name)))
        if not tabs:
            diagnostics.append(_protocol_diagnostic(context, stable_key, before_row, current_row, candidates))
            continue
        consumed.update(str(tab["table_name"]) for tab in tabs)
        items.append(
            {
                "protocol_key": stable_key,
                "board": _parse_channel_key(stable_key)[0],
                "link_no": _parse_channel_key(stable_key)[1],
                "label": _protocol_item_label(stable_key, before_row=before_row, current_row=current_row),
                "tabs": tabs,
            }
        )
    return (
        _base_payload(
            COMMUNICATION_PROTOCOL_PROJECTION_VERSION,
            BusinessProjectionKind.COMMUNICATION_PROTOCOLS,
            items,
            diagnostics,
        ),
        consumed,
        diagnostics,
    )


def _build_secondary_projection(context: _ProjectionContext) -> tuple[dict[str, object], set[str], list[DiagnosticRecord]]:
    before_device_rows = context.table_rows("device", side="before")
    current_device_rows = context.table_rows("device", side="current")
    duplicate_dev_addrs = sorted(_duplicates(before_device_rows, "dev_addr") | _duplicates(current_device_rows, "dev_addr"))
    duplicate_gids = sorted(_duplicates(before_device_rows, "gid") | _duplicates(current_device_rows, "gid"))
    diagnostics: list[DiagnosticRecord] = []
    for value in duplicate_dev_addrs:
        diagnostics.append(_diagnostic("DUPLICATE_DEVICE_ADDRESS", "Duplicate secondary device dev_addr.", {"dev_addr": value}))
    for value in duplicate_gids:
        diagnostics.append(_diagnostic("DUPLICATE_DEVICE_GID", "Duplicate secondary device gid.", {"gid": value}))

    before_by_dev_addr = _index_first_by_int(before_device_rows, "dev_addr")
    current_by_dev_addr = _index_first_by_int(current_device_rows, "dev_addr")
    items: list[dict[str, object]] = []
    consumed: set[str] = set()
    if context.is_visible("device") and context.table_exists("device"):
        consumed.add("device")
        table = context.table("device")
        label = _display_name(table, _SECONDARY_DEVICE_METADATA_LABEL_FALLBACK)
        items.append(
            {
                "device_key": "metadata:device",
                "table_id": "device",
                "table_name": "device",
                "label": label,
                "tabs": [_tab_payload("device", label)],
            }
        )
    for dev_addr in sorted((set(before_by_dev_addr) | set(current_by_dev_addr)) - set(duplicate_dev_addrs)):
        before_row = before_by_dev_addr.get(dev_addr)
        current_row = current_by_dev_addr.get(dev_addr)
        gid = _coerce_int(_row_value(current_row, "gid"))
        if gid is None:
            gid = _coerce_int(_row_value(before_row, "gid"))
        tabs: list[dict[str, object]] = []
        for table_name, label, column_name, identity_key in _SECONDARY_DEVICE_TAB_SPECS:
            if not context.is_visible(table_name) or not context.table_exists(table_name):
                continue
            identity_value = gid if identity_key == "gid" else dev_addr
            if identity_value is None:
                continue
            if identity_key == "gid" and identity_value in duplicate_gids:
                continue
            before_count = len(_filter_rows(context.table_rows(table_name, side="before"), column_name, identity_value))
            current_count = len(_filter_rows(context.table_rows(table_name, side="current"), column_name, identity_value))
            before_loaded = context.table_rows_loaded(table_name, side="before")
            current_loaded = context.table_rows_loaded(table_name, side="current")
            has_unloaded_present_side = (
                (context.table_present(table_name, side="before") and not before_loaded)
                or (context.table_present(table_name, side="current") and not current_loaded)
            )
            if not has_unloaded_present_side and before_count == 0 and current_count == 0:
                continue
            tab = {
                **_tab_payload(table_name, label),
                "row_filter": {
                    "kind": "ITEM_IDENTITY_EQUALS",
                    "column_name": column_name,
                    "identity_key": identity_key,
                    "identity_value": identity_value,
                },
            }
            if before_loaded:
                tab["before_row_count"] = before_count
            if current_loaded:
                tab["current_row_count"] = current_count
            tabs.append(tab)
        items.append(
            {
                "device_key": f"dev_addr:{dev_addr}",
                "dev_addr": dev_addr,
                "gid": gid,
                "label": _coerce_str(_row_value(current_row, "description"))
                or _coerce_str(_row_value(before_row, "description"))
                or str(dev_addr),
                "tabs": tabs,
            }
        )
        consumed.update(str(tab["table_name"]) for tab in tabs)
    return (
        _base_payload(
            SECONDARY_DEVICE_PROJECTION_VERSION,
            BusinessProjectionKind.SECONDARY_DEVICES,
            items,
            diagnostics,
        ),
        consumed,
        diagnostics,
    )


def _build_global_projection(context: _ProjectionContext) -> tuple[dict[str, object], set[str], list[DiagnosticRecord]]:
    items: list[dict[str, object]] = []
    consumed: set[str] = set()
    diagnostics: list[DiagnosticRecord] = []
    emitted_target_tables: set[str] = set()
    for table_name, fallback_label in _GLOBAL_FIXED_TABLES:
        if not context.is_visible(table_name) or not context.table_exists(table_name):
            continue
        table = context.table(table_name)
        label = _display_name(table, fallback_label)
        items.append(
            {
                "global_key": table_name,
                "table_id": table_name,
                "table_name": table_name,
                "label": label,
                "tabs": [_tab_payload(table_name, label)],
            }
        )
        consumed.add(table_name)
        emitted_target_tables.add(table_name)

    if context.is_visible(_APP_CFG_TABLE) and context.table_exists(_APP_CFG_TABLE):
        app_cfg_table = context.table(_APP_CFG_TABLE)
        app_cfg_label = _display_name(app_cfg_table, _APP_CFG_LABEL_FALLBACK)
        items.append(
            {
                "global_key": _APP_CFG_TABLE,
                "table_id": _APP_CFG_TABLE,
                "table_name": _APP_CFG_TABLE,
                "label": app_cfg_label,
                "tabs": [_tab_payload(_APP_CFG_TABLE, app_cfg_label)],
            }
        )
        consumed.add(_APP_CFG_TABLE)
        emitted_target_tables.add(_APP_CFG_TABLE)

        for row_source, row in _combined_app_cfg_rows(context):
            app_name = _coerce_str(_row_value(row, "app_name"))
            raw_table_cfg = _coerce_str(_row_value(row, "table_cfg"))
            if raw_table_cfg is None:
                diagnostics.append(
                    _global_parameter_diagnostic(
                        "MISSING_TABLE_CFG",
                        "Global app config row does not declare table_cfg.",
                        row_source=row_source,
                        app_name=app_name,
                        table_cfg=None,
                    )
                )
                continue

            target_table_name = canonical_identifier(raw_table_cfg)
            if target_table_name in emitted_target_tables:
                diagnostics.append(
                    _global_parameter_diagnostic(
                        "DUPLICATE_TABLE_CFG",
                        "Global app config target table was already emitted.",
                        row_source=row_source,
                        app_name=app_name,
                        table_cfg=raw_table_cfg,
                        resolved_table_name=target_table_name,
                    )
                )
                continue
            if not context.table_exists(target_table_name):
                diagnostics.append(
                    _global_parameter_diagnostic(
                        "TARGET_TABLE_NOT_FOUND",
                        "Global app config target table was not found.",
                        row_source=row_source,
                        app_name=app_name,
                        table_cfg=raw_table_cfg,
                        resolved_table_name=target_table_name,
                    )
                )
                continue
            if not context.is_visible(target_table_name):
                diagnostics.append(
                    _global_parameter_diagnostic(
                        "TARGET_TABLE_FILTERED",
                        "Global app config target table is not part of the surface.",
                        row_source=row_source,
                        app_name=app_name,
                        table_cfg=raw_table_cfg,
                        resolved_table_name=target_table_name,
                    )
                )
                continue

            target_table = context.table(target_table_name)
            target_label = _display_name(target_table, target_table_name)
            items.append(
                {
                    "global_key": target_table_name,
                    "table_id": target_table_name,
                    "table_name": target_table_name,
                    "label": app_name or target_label,
                    "tabs": [_tab_payload(target_table_name, target_label)],
                }
            )
            consumed.add(target_table_name)
            emitted_target_tables.add(target_table_name)

    return (
        _base_payload(
            GLOBAL_PARAMETER_PROJECTION_VERSION,
            BusinessProjectionKind.GLOBAL_PARAMETERS,
            items,
            diagnostics,
        ),
        consumed,
        diagnostics,
    )


def _build_unparsed_projection(context: _ProjectionContext, consumed: set[str]) -> dict[str, object]:
    items = [
        {
            "table_id": table_name,
            "table_name": table_name,
            "label": table_name,
        }
        for table_name in sorted(context.visible_table_names)
        if table_name not in consumed
    ]
    return _base_payload(UNPARSED_TABLE_PROJECTION_VERSION, BusinessProjectionKind.UNPARSED_TABLES, items)


def _combined_net_cfg_rows(context: _ProjectionContext) -> tuple[list[str], dict[str, Mapping[str, object]], dict[str, Mapping[str, object]]]:
    before_order, before_rows = _index_net_cfg_rows(context.table_rows("net_cfg", side="before"))
    current_order, current_rows = _index_net_cfg_rows(context.table_rows("net_cfg", side="current"))
    combined_order = current_order + [key for key in before_order if key not in current_rows]
    return combined_order, before_rows, current_rows


def _combined_app_cfg_rows(context: _ProjectionContext) -> tuple[tuple[str, Mapping[str, object]], ...]:
    current_rows = context.table_rows(_APP_CFG_TABLE, side="current")
    before_rows = context.table_rows(_APP_CFG_TABLE, side="before")
    current_table_cfgs = {
        canonical_table_cfg
        for row in current_rows
        if (canonical_table_cfg := _canonical_app_table_cfg(row)) is not None
    }
    combined: list[tuple[str, Mapping[str, object]]] = [("current", row) for row in current_rows]
    combined.extend(
        ("before", row)
        for row in before_rows
        if (canonical_table_cfg := _canonical_app_table_cfg(row)) is None
        or canonical_table_cfg not in current_table_cfgs
    )
    return tuple(combined)


def _canonical_app_table_cfg(row: Mapping[str, object]) -> str | None:
    table_cfg = _coerce_str(_row_value(row, "table_cfg"))
    if table_cfg is None:
        return None
    return canonical_identifier(table_cfg)


def _index_net_cfg_rows(rows: tuple[Mapping[str, object], ...]) -> tuple[list[str], dict[str, Mapping[str, object]]]:
    ordered: list[str] = []
    by_key: dict[str, Mapping[str, object]] = {}
    for row in rows:
        board = _coerce_int(_row_value(row, "board"))
        link_no = _coerce_int(_row_value(row, "link_no"))
        if board is None or link_no is None:
            continue
        key = f"b{board}_n{link_no}"
        if key in by_key:
            continue
        ordered.append(key)
        by_key[key] = row
    return ordered, by_key


def _forward_protocol_key(row: Mapping[str, object] | None) -> str | None:
    protocol = _protocol_key(row)
    if protocol != "iec104":
        return None
    tab_num = _coerce_int(_row_value(row, "tab_num"))
    if tab_num is None or tab_num <= 0:
        return None
    return protocol


def _protocol_candidates(stable_key: str, *, before_row: Mapping[str, object] | None, current_row: Mapping[str, object] | None) -> tuple[str, ...]:
    segments: list[str] = []
    for row in (current_row, before_row):
        segment = _protocol_segment(row)
        if segment is not None and segment not in segments:
            segments.append(segment)
    candidates: list[str] = []
    for segment in segments:
        candidates.append(f"{stable_key}_{segment}_cfg")
        candidates.append(f"{stable_key}_{segment}_dev_cfg")
    return tuple(candidates)


def _protocol_segment(row: Mapping[str, object] | None) -> str | None:
    protocol = _protocol_key(row)
    if protocol is None:
        return None
    return _PROTOCOL_TABLE_SEGMENT_ALIASES.get(protocol, protocol)


def _protocol_key(row: Mapping[str, object] | None) -> str | None:
    value = _coerce_str(_row_value(row, "exe"))
    return None if value is None else value.lower()


def _protocol_diagnostic(
    context: _ProjectionContext,
    stable_key: str,
    before_row: Mapping[str, object] | None,
    current_row: Mapping[str, object] | None,
    candidates: tuple[str, ...],
) -> DiagnosticRecord:
    if not candidates:
        code = "MISSING_PROTOCOL_EXE"
        message = "Protocol exe is missing for communication channel."
    elif any(context.table_exists(table_name) for table_name in candidates):
        code = "CANDIDATE_TABLE_FILTERED"
        message = "Protocol candidate table exists but is not part of the surface."
    else:
        code = "CANDIDATE_TABLE_NOT_FOUND"
        message = "Protocol candidate table was not found."
    board, link_no = _parse_channel_key(stable_key)
    return _diagnostic(
        code,
        message,
        {
            "stable_key": stable_key,
            "board": board,
            "link_no": link_no,
            "before_exe": _coerce_str(_row_value(before_row, "exe")),
            "current_exe": _coerce_str(_row_value(current_row, "exe")),
            "candidate_table_names": list(candidates),
        },
    )


def _global_parameter_diagnostic(
    code: str,
    message: str,
    *,
    row_source: str,
    app_name: str | None,
    table_cfg: str | None,
    resolved_table_name: str | None = None,
) -> DiagnosticRecord:
    details: dict[str, object] = {
        "row_source": row_source,
        "app_name": app_name,
        "table_cfg": table_cfg,
    }
    if resolved_table_name is not None:
        details["resolved_table_name"] = resolved_table_name
    return _diagnostic(code, message, details)


def _diagnostic(code: str, message: str, details: Mapping[str, object]) -> DiagnosticRecord:
    return DiagnosticRecord(
        code=code,
        message=message,
        phase="business_projection",
        severity="WARNING",
        details=details,
    )


def _tab_payload(table_name: str, label: str) -> dict[str, object]:
    table_id = canonical_identifier(table_name)
    return {
        "tab_id": f"table:{table_id}",
        "label": label,
        "table_id": table_id,
        "table_name": table_id,
    }


def _display_name(table: BusinessProjectionTable | None, fallback: str) -> str:
    if table is not None and table.display_name:
        return table.display_name
    return fallback


def _protocol_item_label(stable_key: str, *, before_row: Mapping[str, object] | None, current_row: Mapping[str, object] | None) -> str:
    channel_desc = _coerce_str(_row_value(current_row, "channel_desc")) or _coerce_str(_row_value(before_row, "channel_desc"))
    protocol_name = _coerce_str(_row_value(current_row, "protocol_name")) or _coerce_str(_row_value(before_row, "protocol_name"))
    if channel_desc and protocol_name:
        return f"{channel_desc} {protocol_name}"
    if channel_desc:
        return channel_desc
    if protocol_name:
        return f"{stable_key} {protocol_name}"
    return stable_key


def _parse_channel_key(stable_key: str) -> tuple[int, int]:
    match = re.fullmatch(r"b(?P<board>\d+)_n(?P<link_no>\d+)", stable_key)
    if match is None:
        raise ValueError(f"invalid channel key: {stable_key}")
    return int(match.group("board")), int(match.group("link_no"))


def _row_value(row: Mapping[str, object] | None, column_name: str) -> object | None:
    if row is None:
        return None
    if column_name in row:
        return row[column_name]
    lowered = column_name.lower()
    for key, value in row.items():
        if str(key).lower() == lowered:
            return value
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        if not text:
            return None
        return int(text)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _duplicates(rows: tuple[Mapping[str, object], ...], column_name: str) -> set[int]:
    counts = Counter(
        value
        for row in rows
        if (value := _coerce_int(_row_value(row, column_name))) is not None
    )
    return {value for value, count in counts.items() if count > 1}


def _index_first_by_int(rows: tuple[Mapping[str, object], ...], column_name: str) -> dict[int, Mapping[str, object]]:
    indexed: dict[int, Mapping[str, object]] = {}
    for row in rows:
        value = _coerce_int(_row_value(row, column_name))
        if value is None or value in indexed:
            continue
        indexed[value] = row
    return indexed


def _filter_rows(rows: tuple[Mapping[str, object], ...], column_name: str, identity_value: object) -> tuple[Mapping[str, object], ...]:
    coerced_identity = _coerce_int(identity_value)
    matched: list[Mapping[str, object]] = []
    for row in rows:
        row_value = _row_value(row, column_name)
        if row_value == identity_value:
            matched.append(row)
            continue
        if coerced_identity is not None and _coerce_int(row_value) == coerced_identity:
            matched.append(row)
    return tuple(matched)


__all__ = ["BusinessProjectionAssembler"]
