from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..risk_evaluation import RiskLevel, RiskReport, RiskTableRisk, highest_risk_level
from ..surface_assembly import ComparisonSurface, SurfaceTable

PREVIEW_SIDEBAR_GROUPS: tuple[tuple[str, str], ...] = (
    ("forward_tables", "转发通道"),
    ("secondary_device_list", "二次装置列表"),
    ("communication_protocol_list", "通讯规约列表"),
    ("global_parameters", "全局参数"),
    ("forward_table_group_info", "转发通道分组信息"),
    ("unparsed_tables", "未解析表"),
)
SUMMARY_TABLE_LABELS: Mapping[str, str] = {
    "device": "装置总表",
    "net_cfg": "网口配置表",
    "app_cfg": "高级应用",
    "project": "工程参数",
    "prot_list": "规约配置",
}


@dataclass(frozen=True, slots=True)
class PreviewPayloadMetadata:
    preview_bundle_id: str
    preview_revision_id: str
    preview_strategy_manifest_digest: str
    workspace_id: str
    baseline_alignment: str
    generated_at: str
    default_view_id: str | None = None
    alignment_report: Mapping[str, Any] = field(default_factory=dict)
    risk_model_version: str = "backend-vnext/risk-model/v1"
    risk_ruleset_hash: str = "backend-vnext/risk-ruleset/v1"


def build_comparison_surface_payload(surface: ComparisonSurface) -> dict[str, Any]:
    if not isinstance(surface, ComparisonSurface):
        raise TypeError("surface must be a ComparisonSurface")
    payload = surface.to_payload()
    payload["schema_version"] = "comparison-surface/v1"
    return _json_mapping(payload)


def build_preview_index_payload(
    *,
    surfaces: Sequence[ComparisonSurface],
    metadata: PreviewPayloadMetadata,
    derived_artifacts_by_view: Mapping[str, Mapping[str, Any]] | None = None,
    table_aliases: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    normalized_surfaces = _surfaces_tuple(surfaces)
    default_view_id = metadata.default_view_id or normalized_surfaces[0].view.view_id
    derived_by_view = dict(derived_artifacts_by_view or {})
    tables: list[dict[str, Any]] = []
    for surface in normalized_surfaces:
        tables.extend(_preview_index_table_payload(surface, table) for table in surface.tables)
    payload = {
        "schema_version": "preview-index/v2",
        "preview_bundle_id": metadata.preview_bundle_id,
        "preview_revision_id": metadata.preview_revision_id,
        "preview_strategy_manifest_digest": metadata.preview_strategy_manifest_digest,
        "workspace_id": metadata.workspace_id,
        "baseline_alignment": _baseline_alignment_payload(metadata.baseline_alignment),
        "alignment_report": _alignment_report_payload(metadata.alignment_report),
        "default_view_id": default_view_id,
        "views": [
            _preview_index_view_payload(surface, derived_by_view.get(surface.view.view_id))
            for surface in normalized_surfaces
        ],
        "tables": tables,
        "sidebar_trees": [_sidebar_tree_payload(surface) for surface in normalized_surfaces],
        "generated_at": metadata.generated_at,
        "bundle_relative_root": ".",
    }
    if table_aliases:
        payload["table_aliases"] = [dict(alias) for alias in table_aliases]
    return payload


def build_diff_summary_payload(
    *,
    surfaces: Sequence[ComparisonSurface],
    metadata: PreviewPayloadMetadata,
) -> dict[str, Any]:
    normalized_surfaces = _surfaces_tuple(surfaces)
    return {
        "schema_version": "diff-summary/v2",
        "preview_revision_id": metadata.preview_revision_id,
        "baseline_alignment": _baseline_alignment_payload(metadata.baseline_alignment),
        "has_external_change_conflict": False,
        "view_summaries": [_diff_view_summary_payload(surface) for surface in normalized_surfaces],
        "table_summaries": [
            _diff_table_summary_payload(surface, table)
            for surface in normalized_surfaces
            for table in surface.tables
        ],
        "generated_at": metadata.generated_at,
    }


def build_risk_report_payload(
    *,
    risk_reports: Sequence[RiskReport],
    surfaces: Sequence[ComparisonSurface],
    metadata: PreviewPayloadMetadata,
) -> dict[str, Any]:
    normalized_surfaces = _surfaces_tuple(surfaces)
    normalized_reports = tuple(risk_reports)
    for report in normalized_reports:
        if not isinstance(report, RiskReport):
            raise TypeError("risk_reports must contain RiskReport values")
    risk_by_table = _risk_by_surface_table(normalized_surfaces, normalized_reports)
    overall = _overall_risk_payload(normalized_reports)
    return {
        "schema_version": "risk-report/v1",
        "risk_model_version": metadata.risk_model_version,
        "risk_ruleset_hash": metadata.risk_ruleset_hash,
        "preview_bundle_id": metadata.preview_bundle_id,
        "preview_revision_id": metadata.preview_revision_id,
        "overall": overall,
        "views": [
            _risk_view_payload(surface, risk_by_table)
            for surface in normalized_surfaces
        ],
        "tables": [
            _risk_table_payload(surface, table, risk_by_table.get((surface.view.view_id, table.table_name)))
            for surface in normalized_surfaces
            for table in surface.tables
        ],
        "sidebar_projection": [
            _risk_sidebar_projection_payload(surface, risk_by_table)
            for surface in normalized_surfaces
        ],
        "annotation_refs": [
            _risk_annotation_ref_payload(surface, table, risk)
            for surface in normalized_surfaces
            for table in surface.tables
            for risk in (risk_by_table.get((surface.view.view_id, table.table_name)),)
            if risk is not None and _annotation_ref_for(table, risk) is not None
        ],
        "generated_at": metadata.generated_at,
    }


def build_alignment_report_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return _alignment_report_payload(value)


def _surfaces_tuple(surfaces: Sequence[ComparisonSurface]) -> tuple[ComparisonSurface, ...]:
    normalized = tuple(surfaces)
    if not normalized:
        raise ValueError("surfaces must contain at least one ComparisonSurface")
    for surface in normalized:
        if not isinstance(surface, ComparisonSurface):
            raise TypeError("surfaces must contain ComparisonSurface values")
    return normalized


def _preview_index_view_payload(
    surface: ComparisonSurface,
    derived_artifacts: Mapping[str, Any] | None,
) -> dict[str, Any]:
    view = surface.view
    from_role = view.display_before_role or view.before_role.value
    to_role = view.display_current_role or view.current_role.value
    payload: dict[str, Any] = {
        "view_id": view.view_id,
        "label": view.label or view.view_id,
        "from_role": from_role,
        "to_role": to_role,
        "from_ref": from_role,
        "to_ref": to_role,
        "changed_table_count": view.changed_table_count,
        "has_structural_change": surface.summary.degraded_table_count > 0,
    }
    if derived_artifacts is not None:
        payload["derived_artifacts"] = dict(derived_artifacts)
    return payload


def _preview_index_table_payload(surface: ComparisonSurface, table: SurfaceTable) -> dict[str, Any]:
    table_payload = table.to_payload()
    table_refs = table_payload.get("table_refs", {})
    records_refs = table_payload.get("records_refs", {})
    before_table_ref = table_refs.get("before_table_ref")
    current_table_ref = table_refs.get("current_table_ref")
    if current_table_ref is None and before_table_ref is None:
        current_table_ref = table_refs.get("browse_table_ref")
    diagnostics = _diagnostics_summary(table)
    ordered_extension = table.ordered_extension
    ordered_position_column = _ordered_position_column(table)
    ordered_preprocess_applied = (
        None if ordered_extension is None else ordered_extension.ordered_preprocess_applied
    )
    return {
        "table_name": table.table_name,
        "display_name": table.display_name,
        "base_table_name": table.table_name,
        "artifact_key": table.table_name,
        "base_table_parent_name": None,
        "group_change_status": "UNCHANGED",
        "view_id": surface.view.view_id,
        "schema_hash": _digest_or_empty(table_payload.get("schema_summary")),
        "content_hash": _digest_or_empty(table_payload.get("records_refs")),
        "row_count": table.row_count or 0,
        "change_kind": table.change_kind.value,
        "row_change_stats": _row_change_stats(table.row_change_stats),
        "columns": [
            {
                "name": column,
                "display_name": column,
                "type": "unknown",
                "display_order": index,
            }
            for index, column in enumerate(table.columns)
        ],
        "base_table_ref": None,
        "before_table_ref": before_table_ref,
        "current_table_ref": current_table_ref,
        "diff_artifact_ref": records_refs.get("records_ref"),
        "diff_artifact_semantics_version": "diff-artifact/v2" if records_refs.get("records_ref") else None,
        "table_processing_mode": table.display.table_processing_mode.value,
        "display_strategy": _display_strategy(table),
        "replay_guarantee": table.display.replay_guarantee.value,
        "stable_key_columns": _stable_key_columns(table),
        "position_column": ordered_position_column,
        "ordered_preprocess_applied": ordered_preprocess_applied,
        "repair_applied": None,
        "diff_diagnostics_ref": None,
        "diff_diagnostics_summary": diagnostics,
        "skipped_row_count": 0,
        "skipped_row_reasons": [],
    }


def _sidebar_tree_payload(surface: ComparisonSurface) -> dict[str, Any]:
    items = [
        {
            "item_key": table.table_name,
            "item_label": _preview_table_label(table.table_name, table.display_name),
            "item_kind": "table",
            "stable_key": table.table_name,
            "raw_table_name": table.table_name,
            "resolved_base_table_name": table.table_name,
            "has_change": table.change_kind.value not in {"UNCHANGED", "BUSINESS_EQUIVALENT"},
            "change_kind": table.change_kind.value,
            "tabs": [
                {
                    "tab_key": table.table_name,
                    "tab_label": _preview_table_label(table.table_name, table.display_name),
                    "table_name": table.table_name,
                    "has_change": table.change_kind.value not in {"UNCHANGED", "BUSINESS_EQUIVALENT"},
                    "change_kind": table.change_kind.value,
                }
            ],
        }
        for table in surface.tables
    ]
    groups = []
    for group_key, group_label in PREVIEW_SIDEBAR_GROUPS:
        group_items = items if group_key == "forward_tables" else []
        groups.append(
            {
                "group_key": group_key,
                "group_label": group_label,
                "has_change": any(item["has_change"] for item in group_items),
                "items": group_items,
            }
        )
    return {
        "view_id": surface.view.view_id,
        "groups": groups,
    }


def _preview_table_label(table_name: str, display_name: str | None) -> str:
    if table_name in SUMMARY_TABLE_LABELS:
        return display_name or SUMMARY_TABLE_LABELS[table_name]
    return table_name


def _diff_view_summary_payload(surface: ComparisonSurface) -> dict[str, Any]:
    return {
        "view_id": surface.view.view_id,
        "label": surface.view.label or surface.view.view_id,
        "changed_table_count": surface.view.changed_table_count,
        "has_structural_change": surface.summary.degraded_table_count > 0,
    }


def _diff_table_summary_payload(surface: ComparisonSurface, table: SurfaceTable) -> dict[str, Any]:
    records_refs = table.records_refs.to_payload()
    stats = _row_change_stats(table.row_change_stats)
    diagnostics = _diagnostics_summary(table)
    return {
        "view_id": surface.view.view_id,
        "table_name": table.table_name,
        "base_table_name": table.table_name,
        "change_kind": table.change_kind.value,
        "schema_changed": table.change_kind.value in {"SCHEMA_CHANGED", "DEGRADED", "FAILED"},
        "data_changed": table.change_kind.value not in {"UNCHANGED", "BUSINESS_EQUIVALENT"},
        "inserted_rows": stats["inserted"],
        "updated_rows": stats["updated"],
        "deleted_rows": stats["deleted"],
        "diff_artifact_ref": records_refs.get("records_ref"),
        "diff_artifact_semantics_version": "diff-artifact/v2" if records_refs.get("records_ref") else None,
        "table_processing_mode": table.display.table_processing_mode.value,
        "replay_guarantee": table.display.replay_guarantee.value,
        "diff_diagnostics_ref": None,
        "diff_diagnostics_summary": diagnostics,
    }


def _risk_by_surface_table(
    surfaces: tuple[ComparisonSurface, ...],
    risk_reports: tuple[RiskReport, ...],
) -> dict[tuple[str, str], RiskTableRisk]:
    risks: dict[tuple[str, str], RiskTableRisk] = {}
    for surface, report in zip(surfaces, risk_reports, strict=False):
        for table_risk in report.tables:
            risks[(surface.view.view_id, table_risk.table_name)] = table_risk
    return risks


def _overall_risk_payload(risk_reports: tuple[RiskReport, ...]) -> dict[str, Any]:
    if not risk_reports:
        return {"risk_level": "UNKNOWN", "reason_codes": []}
    reason_codes: list[str] = []
    for report in risk_reports:
        reason_codes.extend(report.overall.reason_codes)
    return {
        "risk_level": highest_risk_level(report.overall.risk_level for report in risk_reports).value,
        "reason_codes": sorted(set(reason_codes)),
    }


def _risk_view_payload(
    surface: ComparisonSurface,
    risk_by_table: Mapping[tuple[str, str], RiskTableRisk],
) -> dict[str, Any]:
    risks = [
        risk
        for table in surface.tables
        for risk in (risk_by_table.get((surface.view.view_id, table.table_name)),)
        if risk is not None
    ]
    return {
        "view_id": surface.view.view_id,
        "risk_level": _highest_risk_level_payload(tuple(risk.risk_level for risk in risks)),
        "reason_codes": sorted({code for risk in risks for code in risk.reason_codes}),
        "annotation_count": sum(risk.annotation_count for risk in risks),
    }


def _risk_table_payload(
    surface: ComparisonSurface,
    table: SurfaceTable,
    risk: RiskTableRisk | None,
) -> dict[str, Any]:
    return {
        "view_id": surface.view.view_id,
        "table_name": table.table_name,
        "risk_level": risk.risk_level.value if risk is not None else None,
        "reason_codes": list(risk.reason_codes) if risk is not None else [],
        "annotation_count": risk.annotation_count if risk is not None else 0,
        "annotation_ref": _annotation_ref_for(table, risk) if risk is not None else None,
    }


def _risk_sidebar_projection_payload(
    surface: ComparisonSurface,
    risk_by_table: Mapping[tuple[str, str], RiskTableRisk],
) -> dict[str, Any]:
    items = []
    for table in surface.tables:
        risk = risk_by_table.get((surface.view.view_id, table.table_name))
        items.append(
            {
                "item_key": table.table_name,
                "risk_level": risk.risk_level.value if risk is not None else None,
                "reason_codes": list(risk.reason_codes) if risk is not None else [],
            }
        )
    return {
        "view_id": surface.view.view_id,
        "groups": [
            {
                "group_key": "tables",
                "risk_level": _highest_risk_level_payload(
                    tuple(
                        RiskLevel(item["risk_level"])
                        for item in items
                        if item["risk_level"] is not None
                    )
                ),
                "reason_codes": sorted({code for item in items for code in item["reason_codes"]}),
                "items": items,
            }
        ],
    }


def _risk_annotation_ref_payload(
    surface: ComparisonSurface,
    table: SurfaceTable,
    risk: RiskTableRisk,
) -> dict[str, Any]:
    return {
        "view_id": surface.view.view_id,
        "table_name": table.table_name,
        "ref": _annotation_ref_for(table, risk),
    }


def _annotation_ref_for(table: SurfaceTable, risk: RiskTableRisk | None) -> str | None:
    if risk is None or risk.annotation_ref is None:
        return None
    if table.risk_refs.annotation_ref is not None:
        return table.risk_refs.annotation_ref
    return f"risk_artifacts/{risk.table_name}.risk.json"


def _highest_risk_level_payload(levels: tuple[RiskLevel, ...]) -> str | None:
    if not levels:
        return None
    return highest_risk_level(levels).value


def _row_change_stats(value: Mapping[str, object] | None) -> dict[str, int | None]:
    source = dict(value or {})
    return {
        "inserted": _int_value(source.get("inserted")),
        "updated": _int_value(source.get("updated")),
        "deleted": _int_value(source.get("deleted")),
        "unchanged": _optional_int_value(source.get("unchanged")),
    }


def _diagnostics_summary(table: SurfaceTable) -> dict[str, Any] | None:
    if not table.diagnostics and table.display.table_processing_mode.value != "DEGRADED":
        return None
    return {
        "classification_complete": table.display.table_processing_mode.value != "DEGRADED",
        "degraded": table.display.table_processing_mode.value == "DEGRADED",
        "degrade_reason": table.diagnostics[0].code if table.diagnostics else None,
        "replay_guarantee": table.display.replay_guarantee.value,
        "semantic_op_count": None,
        "ambiguous_backbone_candidate_count": None,
        "ambiguous_segment_count": 0,
    }


def _display_strategy(table: SurfaceTable) -> str:
    if table.table_refs.current_table_ref is not None:
        if table.display.table_processing_mode.value == "DEGRADED":
            return "CURRENT_ONLY"
        if table.ordered_extension is not None and table.records_refs.records_ref is not None:
            return "CURRENT_SLOTTED"
        if table.records_refs.records_ref is not None:
            return "CURRENT_INLINE"
        return "CURRENT_ONLY"
    if table.table_refs.before_table_ref is not None:
        return "BEFORE_ONLY"
    if table.table_refs.browse_table_ref is not None:
        return "CURRENT_ONLY"
    return "SUMMARY_ONLY"


def _stable_key_columns(table: SurfaceTable) -> list[str]:
    ordered_extension = table.ordered_extension
    if ordered_extension is not None and ordered_extension.stable_key_field is not None:
        return [ordered_extension.stable_key_field]
    return list(table.compare.compare_key_columns)


def _ordered_position_column(table: SurfaceTable) -> str | None:
    ordered_extension = table.ordered_extension
    if ordered_extension is None:
        return None
    if ordered_extension.position_field is not None:
        return ordered_extension.position_field
    if "no" in table.columns:
        return "no"
    return None


def _alignment_report_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    payload.setdefault("schema_version", "alignment-report/v1")
    payload.setdefault("rule_version", "alignment/v1")
    payload.setdefault("compare_scope", "ALL_TABLES")
    payload.setdefault("compare_mode", "TABLE_FINGERPRINTS")
    payload.setdefault("matched_target_type", None)
    payload.setdefault("matched_workspace_id", None)
    payload.setdefault("matched_preview_role", None)
    payload.setdefault("matched_commit_hash", None)
    payload.setdefault("is_equal_to_baseline", bool(payload.get("status") == "ALIGNED"))
    payload.setdefault("matched_table_count", 0)
    payload.setdefault("mismatched_table_count", 0)
    payload.setdefault("ignored_table_count", 0)
    payload.setdefault("mismatched_tables", [])
    payload.setdefault("compared_targets", [])
    return payload


def _baseline_alignment_payload(value: str) -> str:
    if value in {
        "NOT_EVALUATED",
        "ALIGNED",
        "MATCHED_BATCH_PEER",
        "MATCHED_OTHER_WORKSPACE",
        "PENDING_SUMMARY",
        "EXTERNAL_CHANGE_DETECTED",
    }:
        return value
    if value in {"", "NORMAL"}:
        return "NOT_EVALUATED"
    return "NOT_EVALUATED"


def _digest_or_empty(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("schema_digest", "content_digest", "records_content_digest", "records_manifest_digest"):
            nested = value.get(key)
            if isinstance(nested, str):
                return nested
    return ""


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _optional_int_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _json_mapping(value: Mapping[str, object]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


__all__ = [
    "PreviewPayloadMetadata",
    "build_comparison_surface_payload",
    "build_diff_summary_payload",
    "build_preview_index_payload",
    "build_risk_report_payload",
]
