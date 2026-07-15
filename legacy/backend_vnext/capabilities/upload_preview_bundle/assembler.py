from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from shutil import copyfile
from time import perf_counter
from typing import Any, Mapping

from ..bundle_assembly.bundle_assembler import (
    BundleAssembler as CoreBundleAssembler,
)
from ..bundle_assembly.bundle_assembler import (
    BundleAssemblyRequest as CoreBundleAssemblyRequest,
)
from ..bundle_assembly.bundle_assembler import (
    BundleAssemblyResult as CoreBundleAssemblyResult,
)
from ..bundle_assembly.bundle_assembler import BundleRefs as UploadPreviewBundleRefs
from ..risk_evaluation import (
    RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION,
    RiskReport,
)
from ..surface_assembly import ComparisonSurface
from ...core.validation import ensure_bundle_relative_path
from ...core.validation import require_non_empty
from ...tarball import TarballMetadata, create_stable_tarball
from .payloads import (
    PREVIEW_SIDEBAR_GROUPS,
    PreviewPayloadMetadata,
    build_alignment_report_payload,
    build_comparison_surface_payload,
    build_diff_summary_payload,
    build_preview_index_payload,
    build_risk_report_payload,
)

SUMMARY_TABLE_LABELS: Mapping[str, str] = {
    "device": "装置总表",
    "net_cfg": "网口配置表",
    "app_cfg": "高级应用",
    "project": "工程参数",
    "prot_list": "规约配置",
}


@dataclass(frozen=True, slots=True)
class BundleArtifact:
    relative_ref: str
    json_payload: Mapping[str, Any] | None = None
    content_bytes: bytes | None = None
    source_path: Path | None = None

    def __post_init__(self) -> None:
        _ensure_bundle_artifact_ref(self.relative_ref)
        if self.relative_ref.endswith("/"):
            raise ValueError("relative_ref must point to a file")
        has_json = self.json_payload is not None
        has_bytes = self.content_bytes is not None
        has_source_path = self.source_path is not None
        if sum((has_json, has_bytes, has_source_path)) != 1:
            raise ValueError(
                "exactly one of json_payload, content_bytes, or source_path is required"
            )
        if self.json_payload is not None and not isinstance(self.json_payload, Mapping):
            raise TypeError("json_payload must be a mapping or None")
        if self.content_bytes is not None and not isinstance(self.content_bytes, bytes):
            object.__setattr__(self, "content_bytes", bytes(self.content_bytes))
        if self.source_path is not None:
            if not isinstance(self.source_path, Path):
                raise TypeError("source_path must be a Path or None")
            if not self.source_path.is_file():
                raise ValueError("source_path must point to an existing file")

    @classmethod
    def json(cls, relative_ref: str, payload: Mapping[str, Any]) -> "BundleArtifact":
        return cls(relative_ref=relative_ref, json_payload=payload)

    @classmethod
    def bytes(cls, relative_ref: str, content: bytes | bytearray | memoryview) -> "BundleArtifact":
        return cls(relative_ref=relative_ref, content_bytes=bytes(content))

    @classmethod
    def file(cls, relative_ref: str, source_path: Path) -> "BundleArtifact":
        return cls(relative_ref=relative_ref, source_path=source_path)


@dataclass(frozen=True, slots=True)
class UploadPreviewBundleRequest:
    bundle_root: Path
    preview_bundle_id: str
    preview_revision_id: str
    preview_strategy_manifest_digest: str
    workspace_id: str
    baseline_alignment: str
    default_view_id: str
    generated_at: str
    preview_strategy_manifest: Mapping[str, Any]
    alignment_report: Mapping[str, Any]
    views: tuple[Mapping[str, Any], ...]
    tables: tuple[Mapping[str, Any], ...]
    sidebar_trees: tuple[Mapping[str, Any], ...]
    comparison_surface: Mapping[str, Any]
    diff_summary: Mapping[str, Any]
    risk_report: Mapping[str, Any]
    refs: UploadPreviewBundleRefs = field(default_factory=UploadPreviewBundleRefs)
    derived_artifacts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    table_aliases: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    bundle_artifacts: tuple[BundleArtifact, ...] = field(default_factory=tuple)
    tar_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bundle_root, Path):
            raise TypeError("bundle_root must be a Path")
        if self.tar_path is not None and not isinstance(self.tar_path, Path):
            raise TypeError("tar_path must be a Path or None")
        for field_name in (
            "preview_bundle_id",
            "preview_revision_id",
            "preview_strategy_manifest_digest",
            "workspace_id",
            "baseline_alignment",
            "default_view_id",
            "generated_at",
        ):
            require_non_empty(str(getattr(self, field_name)), field_name)
        if not isinstance(self.bundle_artifacts, tuple):
            object.__setattr__(self, "bundle_artifacts", tuple(self.bundle_artifacts))
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        for alias in self.table_aliases:
            if not isinstance(alias, Mapping):
                raise TypeError("table_aliases must contain mapping values")
        for artifact in self.bundle_artifacts:
            if not isinstance(artifact, BundleArtifact):
                raise TypeError("bundle_artifacts must contain BundleArtifact values")


@dataclass(frozen=True, slots=True)
class UploadPreviewBundlePayloadInput:
    bundle_root: Path
    preview_bundle_id: str
    preview_revision_id: str
    preview_strategy_manifest_digest: str
    workspace_id: str
    baseline_alignment: str
    generated_at: str
    surfaces: tuple[ComparisonSurface, ...]
    risk_reports: tuple[RiskReport, ...] = field(default_factory=tuple)
    default_view_id: str | None = None
    preview_strategy_manifest: Mapping[str, Any] = field(default_factory=dict)
    alignment_report: Mapping[str, Any] = field(default_factory=dict)
    refs: UploadPreviewBundleRefs = field(default_factory=UploadPreviewBundleRefs)
    derived_artifacts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    derived_artifacts_by_view: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    table_aliases: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    bundle_artifacts: tuple[BundleArtifact, ...] = field(default_factory=tuple)
    tar_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bundle_root, Path):
            raise TypeError("bundle_root must be a Path")
        if self.tar_path is not None and not isinstance(self.tar_path, Path):
            raise TypeError("tar_path must be a Path or None")
        if not isinstance(self.surfaces, tuple):
            object.__setattr__(self, "surfaces", tuple(self.surfaces))
        if not self.surfaces:
            raise ValueError("surfaces must contain at least one ComparisonSurface")
        for surface in self.surfaces:
            if not isinstance(surface, ComparisonSurface):
                raise TypeError("surfaces must contain ComparisonSurface values")
        if not isinstance(self.risk_reports, tuple):
            object.__setattr__(self, "risk_reports", tuple(self.risk_reports))
        for risk_report in self.risk_reports:
            if not isinstance(risk_report, RiskReport):
                raise TypeError("risk_reports must contain RiskReport values")
        for field_name in (
            "preview_bundle_id",
            "preview_revision_id",
            "preview_strategy_manifest_digest",
            "workspace_id",
            "baseline_alignment",
            "generated_at",
        ):
            require_non_empty(str(getattr(self, field_name)), field_name)
        if self.default_view_id is not None:
            require_non_empty(self.default_view_id, "default_view_id")
        if not isinstance(self.bundle_artifacts, tuple):
            object.__setattr__(self, "bundle_artifacts", tuple(self.bundle_artifacts))
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        for alias in self.table_aliases:
            if not isinstance(alias, Mapping):
                raise TypeError("table_aliases must contain mapping values")
        for artifact in self.bundle_artifacts:
            if not isinstance(artifact, BundleArtifact):
                raise TypeError("bundle_artifacts must contain BundleArtifact values")


@dataclass(frozen=True, slots=True)
class UploadPreviewBundleResult:
    bundle_root: Path
    manifest_path: Path
    preview_index_path: Path
    alignment_report_path: Path
    comparison_surface_path: Path
    diff_summary_path: Path
    risk_report_path: Path
    strategy_manifest_path: Path
    derived_artifact_paths: Mapping[str, Path]
    manifest: Mapping[str, Any]
    preview_index: Mapping[str, Any]
    tarball: TarballMetadata | None = None
    bundle_write_duration_ms: int | None = None
    tar_create_duration_ms: int | None = None


class UploadPreviewBundleAssembler:
    def __init__(
        self,
        *,
        sidecar_assembler: CoreBundleAssembler | None = None,
    ) -> None:
        self._sidecar_assembler = sidecar_assembler or CoreBundleAssembler()
        if not isinstance(self._sidecar_assembler, CoreBundleAssembler):
            raise TypeError("sidecar_assembler must be a preview-compatible BundleAssembler")

    def assemble(self, request: UploadPreviewBundleRequest) -> UploadPreviewBundleResult:
        if not isinstance(request, UploadPreviewBundleRequest):
            raise TypeError("request must be a UploadPreviewBundleRequest")
        bundle_write_started_at = perf_counter()
        sidecar_result = self._sidecar_assembler.assemble(_sidecar_request(request))
        _validate_preview_row_artifact_closure(
            preview_index=sidecar_result.preview_index,
            comparison_surface=request.comparison_surface,
            artifacts=request.bundle_artifacts,
        )
        _validate_preview_risk_annotation_closure(
            risk_report=request.risk_report,
            comparison_surface=request.comparison_surface,
            artifacts=request.bundle_artifacts,
        )
        _write_bundle_artifacts(
            bundle_root=sidecar_result.bundle_root,
            refs=request.refs,
            artifacts=request.bundle_artifacts,
        )
        bundle_write_duration_ms = int(round((perf_counter() - bundle_write_started_at) * 1000))
        tar_create_started_at = perf_counter()
        tarball = (
            create_stable_tarball(
                source_root=sidecar_result.bundle_root,
                tar_path=request.tar_path,
            )
            if request.tar_path is not None
            else None
        )
        tar_create_duration_ms = (
            None
            if tarball is None
            else int(round((perf_counter() - tar_create_started_at) * 1000))
        )
        return _preview_result(
            sidecar_result,
            tarball,
            bundle_write_duration_ms=bundle_write_duration_ms,
            tar_create_duration_ms=tar_create_duration_ms,
        )

    def assemble_payloads(
        self,
        payload_input: UploadPreviewBundlePayloadInput,
    ) -> UploadPreviewBundleResult:
        return self.assemble(build_upload_preview_bundle_request(payload_input))


def build_upload_preview_bundle_request(
    payload_input: UploadPreviewBundlePayloadInput,
) -> UploadPreviewBundleRequest:
    if not isinstance(payload_input, UploadPreviewBundlePayloadInput):
        raise TypeError("payload_input must be a UploadPreviewBundlePayloadInput")
    metadata = PreviewPayloadMetadata(
        preview_bundle_id=payload_input.preview_bundle_id,
        preview_revision_id=payload_input.preview_revision_id,
        preview_strategy_manifest_digest=payload_input.preview_strategy_manifest_digest,
        workspace_id=payload_input.workspace_id,
        baseline_alignment=payload_input.baseline_alignment,
        generated_at=payload_input.generated_at,
        default_view_id=payload_input.default_view_id,
        alignment_report=payload_input.alignment_report,
    )
    derived_artifacts_by_view = {
        view_id: {
            **dict(payload_input.derived_artifacts_by_view.get(view_id, {})),
            "comparison_surface_ref": f"pairs/{view_id}/comparison-surface.json",
        }
        for view_id in (surface.view.view_id for surface in payload_input.surfaces)
    }
    preview_index = build_preview_index_payload(
        surfaces=payload_input.surfaces,
        metadata=metadata,
        derived_artifacts_by_view=derived_artifacts_by_view,
        table_aliases=payload_input.table_aliases,
    )
    comparison_surface_payloads = {
        surface.view.view_id: build_comparison_surface_payload(surface)
        for surface in payload_input.surfaces
    }
    default_view_id = str(preview_index["default_view_id"])
    default_comparison_surface = comparison_surface_payloads.get(default_view_id)
    if default_comparison_surface is None:
        default_comparison_surface = build_comparison_surface_payload(payload_input.surfaces[0])
    per_view_surface_artifacts = tuple(
        BundleArtifact.json(
            f"pairs/{view_id}/comparison-surface.json",
            surface_payload,
        )
        for view_id, surface_payload in sorted(comparison_surface_payloads.items())
    )
    return UploadPreviewBundleRequest(
        bundle_root=payload_input.bundle_root,
        preview_bundle_id=payload_input.preview_bundle_id,
        preview_revision_id=payload_input.preview_revision_id,
        preview_strategy_manifest_digest=payload_input.preview_strategy_manifest_digest,
        workspace_id=payload_input.workspace_id,
        baseline_alignment=payload_input.baseline_alignment,
        default_view_id=default_view_id,
        generated_at=payload_input.generated_at,
        preview_strategy_manifest=_preview_strategy_manifest_payload(payload_input),
        alignment_report=metadata.alignment_report,
        views=tuple(preview_index["views"]),
        tables=tuple(preview_index["tables"]),
        sidebar_trees=tuple(preview_index["sidebar_trees"]),
        comparison_surface=default_comparison_surface,
        diff_summary=build_diff_summary_payload(
            surfaces=payload_input.surfaces,
            metadata=metadata,
        ),
        risk_report=build_risk_report_payload(
            risk_reports=payload_input.risk_reports,
            surfaces=payload_input.surfaces,
            metadata=metadata,
        ),
        refs=payload_input.refs,
        derived_artifacts=payload_input.derived_artifacts,
        table_aliases=payload_input.table_aliases,
        bundle_artifacts=(*payload_input.bundle_artifacts, *per_view_surface_artifacts),
        tar_path=payload_input.tar_path,
    )


def _sidecar_request(
    request: UploadPreviewBundleRequest,
) -> CoreBundleAssemblyRequest:
    baseline_alignment = _preview_baseline_alignment(request.baseline_alignment)
    return CoreBundleAssemblyRequest(
        bundle_root=request.bundle_root,
        preview_bundle_id=request.preview_bundle_id,
        preview_revision_id=request.preview_revision_id,
        preview_strategy_manifest_digest=request.preview_strategy_manifest_digest,
        workspace_id=request.workspace_id,
        baseline_alignment=baseline_alignment,
        default_view_id=request.default_view_id,
        generated_at=request.generated_at,
        preview_strategy_manifest=request.preview_strategy_manifest,
        alignment_report=build_alignment_report_payload(request.alignment_report),
        views=request.views,
        tables=_preview_preview_tables(request.tables),
        sidebar_trees=_preview_sidebar_trees(request.sidebar_trees, request.tables),
        comparison_surface=request.comparison_surface,
        diff_summary=_preview_diff_summary_payload(
            request.diff_summary,
            baseline_alignment=baseline_alignment,
        ),
        risk_report=request.risk_report,
        refs=request.refs,
        derived_artifacts=request.derived_artifacts,
        table_aliases=request.table_aliases,
    )


def _preview_baseline_alignment(value: str) -> str:
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


def _preview_diff_summary_payload(
    value: Mapping[str, Any],
    *,
    baseline_alignment: str,
) -> dict[str, Any]:
    payload = dict(value)
    payload["baseline_alignment"] = _preview_baseline_alignment(
        str(payload.get("baseline_alignment") or baseline_alignment)
    )
    return payload


def _preview_preview_tables(tables: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    return tuple(_preview_preview_table(table) for table in tables)


def _preview_preview_table(table: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(table)
    payload.setdefault("display_name", payload.get("table_name", ""))
    payload.setdefault("base_table_name", payload.get("table_name", ""))
    payload.setdefault("artifact_key", payload.get("table_name", ""))
    payload.setdefault("base_table_parent_name", None)
    payload["group_change_status"] = "UNCHANGED"
    payload.setdefault("schema_hash", "")
    payload.setdefault("content_hash", "")
    payload.setdefault("row_count", 0)
    payload.setdefault("change_kind", "UNCHANGED")
    payload.setdefault("row_change_stats", {})
    payload["columns"] = _preview_preview_columns(payload.get("columns"))
    payload.setdefault("stable_key_columns", [])
    payload.setdefault("position_column", None)
    return payload


def _preview_preview_columns(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    columns: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or item.get("column_name") or "")
        if not name:
            continue
        column = dict(item)
        column["name"] = name
        column["display_name"] = str(column.get("display_name") or name)
        column["type"] = str(column.get("type") or "unknown")
        column.setdefault("display_order", index)
        columns.append(column)
    return columns


def _preview_sidebar_trees(
    trees: tuple[Mapping[str, Any], ...],
    tables: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(_preview_sidebar_tree(tree, tables) for tree in trees)


def _preview_sidebar_tree(tree: Mapping[str, Any], tables: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    payload = dict(tree)
    view_id = str(payload.get("view_id") or "")
    groups_by_key = {
        str(group.get("group_key")): dict(group)
        for group in payload.get("groups", ())
        if isinstance(group, Mapping) and group.get("group_key") is not None
    }
    normalized_groups: list[dict[str, Any]] = []
    for group_key, group_label in PREVIEW_SIDEBAR_GROUPS:
        group = groups_by_key.pop(group_key, None)
        if group is None and group_key == "forward_tables":
            preview_tables = groups_by_key.pop("tables", None)
            group = preview_tables
        items = group.get("items") if group is not None else []
        if not isinstance(items, (list, tuple)):
            items = []
        if group_key == "forward_tables" and not items:
            items = _preview_sidebar_items_from_tables(view_id=view_id, tables=tables)
        normalized_groups.append(
            {
                "group_key": group_key,
                "group_label": str((group or {}).get("group_label") or group_label),
                "has_change": bool((group or {}).get("has_change") or False),
                "items": list(items),
            }
        )
    payload["groups"] = normalized_groups
    return payload


def _preview_sidebar_items_from_tables(
    *,
    view_id: str,
    tables: tuple[Mapping[str, Any], ...],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for table in tables:
        if view_id and table.get("view_id") != view_id:
            continue
        table_name = str(table.get("table_name") or "")
        if not table_name:
            continue
        label = _preview_table_label(table_name, table.get("display_name"))
        change_kind = str(table.get("change_kind") or "UNCHANGED")
        has_change = change_kind not in {"UNCHANGED", "BUSINESS_EQUIVALENT"}
        items.append(
            {
                "item_key": table_name,
                "item_label": label,
                "item_kind": "table",
                "stable_key": table_name,
                "raw_table_name": table_name,
                "resolved_base_table_name": table.get("base_table_name") or table_name,
                "has_change": has_change,
                "change_kind": change_kind,
                "tabs": [
                    {
                        "tab_key": table_name,
                        "tab_label": label,
                        "table_name": table_name,
                        "has_change": has_change,
                        "change_kind": change_kind,
                    }
                ],
            }
        )
    return items


def _preview_table_label(table_name: str, display_name: object) -> str:
    if table_name in SUMMARY_TABLE_LABELS:
        return str(display_name or SUMMARY_TABLE_LABELS[table_name])
    return table_name


def _preview_strategy_manifest_payload(
    payload_input: UploadPreviewBundlePayloadInput,
) -> Mapping[str, Any]:
    if payload_input.preview_strategy_manifest:
        return payload_input.preview_strategy_manifest
    return {
        "schema_version": "preview-strategy-manifest/v2",
        "preview_revision_id": payload_input.preview_revision_id,
        "preview_strategy_manifest_digest": payload_input.preview_strategy_manifest_digest,
    }


_PREVIEW_ROW_REF_FIELDS = (
    "base_table_ref",
    "before_table_ref",
    "current_table_ref",
    "diff_artifact_ref",
)


def _validate_preview_row_artifact_closure(
    *,
    preview_index: Mapping[str, Any],
    comparison_surface: Mapping[str, Any],
    artifacts: tuple[BundleArtifact, ...],
) -> None:
    artifacts_by_ref: dict[str, BundleArtifact] = {}
    for artifact in artifacts:
        if artifact.relative_ref in artifacts_by_ref:
            raise ValueError(f"duplicate bundle artifact ref: {artifact.relative_ref}")
        artifacts_by_ref[artifact.relative_ref] = artifact

    raw_tables = preview_index.get("tables")
    if not isinstance(raw_tables, list):
        raise ValueError("preview_index.tables must be a list")
    for table in raw_tables:
        if not isinstance(table, Mapping):
            raise ValueError("preview_index.tables must contain mappings")
        table_name = table.get("table_name")
        for field_name in _PREVIEW_ROW_REF_FIELDS:
            _require_parquet_artifact(
                artifacts_by_ref=artifacts_by_ref,
                ref=table.get(field_name),
                label=f"preview_index {table_name}/{field_name}",
            )

    raw_surface_tables = comparison_surface.get("tables")
    if not isinstance(raw_surface_tables, list):
        raise ValueError("comparison_surface.tables must be a list")
    for table in raw_surface_tables:
        if not isinstance(table, Mapping):
            raise ValueError("comparison_surface.tables must contain mappings")
        records_refs = table.get("records_refs")
        if not isinstance(records_refs, Mapping):
            continue
        table_name = table.get("table_name")
        _require_parquet_artifact(
            artifacts_by_ref=artifacts_by_ref,
            ref=records_refs.get("records_ref"),
            label=f"comparison_surface {table_name}/records_ref",
        )
        manifest_ref = records_refs.get("records_manifest_ref")
        if manifest_ref is not None:
            _require_artifact(
                artifacts_by_ref=artifacts_by_ref,
                ref=manifest_ref,
                label=f"comparison_surface {table_name}/records_manifest_ref",
            )


def _require_parquet_artifact(
    *,
    artifacts_by_ref: Mapping[str, BundleArtifact],
    ref: object,
    label: str,
) -> None:
    if ref is None:
        return
    if not isinstance(ref, str) or not ref.endswith(".parquet"):
        raise ValueError(f"{label} must reference a .parquet artifact")
    artifact = _require_artifact(artifacts_by_ref=artifacts_by_ref, ref=ref, label=label)
    if not _is_parquet_artifact(artifact):
        raise ValueError(f"{label} must reference Parquet bytes, not a metadata payload")


def _require_artifact(
    *,
    artifacts_by_ref: Mapping[str, BundleArtifact],
    ref: object,
    label: str,
) -> BundleArtifact:
    if not isinstance(ref, str) or not ref:
        raise ValueError(f"{label} must be a non-empty bundle-relative ref")
    artifact = artifacts_by_ref.get(ref)
    if artifact is None:
        raise ValueError(f"{label} references missing bundle artifact {ref}")
    return artifact


def _is_parquet_bytes(content: bytes) -> bool:
    return len(content) >= 8 and content.startswith(b"PAR1") and content.endswith(b"PAR1")


def _is_parquet_artifact(artifact: BundleArtifact) -> bool:
    if artifact.content_bytes is not None:
        return _is_parquet_bytes(artifact.content_bytes)
    source_path = artifact.source_path
    if source_path is None:
        return False
    if source_path.stat().st_size < 8:
        return False
    with source_path.open("rb") as handle:
        prefix = handle.read(4)
        handle.seek(-4, 2)
        suffix = handle.read(4)
    return prefix == b"PAR1" and suffix == b"PAR1"


def _validate_preview_risk_annotation_closure(
    *,
    risk_report: Mapping[str, Any],
    comparison_surface: Mapping[str, Any],
    artifacts: tuple[BundleArtifact, ...],
) -> None:
    artifacts_by_ref: dict[str, BundleArtifact] = {}
    for artifact in artifacts:
        artifacts_by_ref[artifact.relative_ref] = artifact

    report_refs = _risk_report_annotation_refs(risk_report)
    for ref, table_name in report_refs.items():
        _require_risk_annotation_content_artifact(
            artifacts_by_ref=artifacts_by_ref,
            ref=ref,
            table_name=table_name,
            label=f"risk_report {table_name}/annotation_ref",
        )

    raw_surface_tables = comparison_surface.get("tables")
    if not isinstance(raw_surface_tables, list):
        raise ValueError("comparison_surface.tables must be a list")
    for table in raw_surface_tables:
        if not isinstance(table, Mapping):
            raise ValueError("comparison_surface.tables must contain mappings")
        table_name = str(table.get("table_name") or "")
        risk_refs = table.get("risk_refs")
        if not isinstance(risk_refs, Mapping):
            continue
        annotation_ref = risk_refs.get("annotation_ref")
        annotation_manifest_ref = risk_refs.get("annotation_manifest_ref")
        if annotation_ref is None and annotation_manifest_ref is None:
            continue
        if not isinstance(annotation_ref, str) or not annotation_ref:
            raise ValueError(f"comparison_surface {table_name}/annotation_ref must be a non-empty ref")
        _require_risk_annotation_content_artifact(
            artifacts_by_ref=artifacts_by_ref,
            ref=annotation_ref,
            table_name=table_name,
            label=f"comparison_surface {table_name}/annotation_ref",
        )
        if not isinstance(annotation_manifest_ref, str) or not annotation_manifest_ref:
            raise ValueError(
                f"comparison_surface {table_name}/annotation_manifest_ref must be a non-empty ref"
            )
        _require_risk_annotation_manifest_artifact(
            artifacts_by_ref=artifacts_by_ref,
            ref=annotation_manifest_ref,
            table_name=table_name,
            label=f"comparison_surface {table_name}/annotation_manifest_ref",
        )


def _risk_report_annotation_refs(risk_report: Mapping[str, Any]) -> dict[str, str]:
    refs: dict[str, str] = {}
    raw_annotation_refs = risk_report.get("annotation_refs")
    if isinstance(raw_annotation_refs, list):
        for item in raw_annotation_refs:
            if not isinstance(item, Mapping):
                continue
            ref = item.get("ref")
            table_name = item.get("table_name")
            if isinstance(ref, str) and ref and isinstance(table_name, str) and table_name:
                refs[ref] = table_name
    raw_tables = risk_report.get("tables")
    if isinstance(raw_tables, list):
        for table in raw_tables:
            if not isinstance(table, Mapping):
                continue
            ref = table.get("annotation_ref")
            table_name = table.get("table_name")
            if isinstance(ref, str) and ref and isinstance(table_name, str) and table_name:
                refs[ref] = table_name
    return refs


def _require_risk_annotation_content_artifact(
    *,
    artifacts_by_ref: Mapping[str, BundleArtifact],
    ref: object,
    table_name: str,
    label: str,
) -> None:
    if not isinstance(ref, str) or not ref.endswith(".json"):
        raise ValueError(f"{label} must reference a .json risk annotation artifact")
    artifact = _require_artifact(artifacts_by_ref=artifacts_by_ref, ref=ref, label=label)
    payload = _require_json_artifact_payload(artifact, label)
    if payload.get("schema_version") != RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION:
        raise ValueError(f"{label} must use {RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION}")
    if payload.get("table_name") != table_name:
        raise ValueError(f"{label} table_name does not match {table_name}")
    if not isinstance(payload.get("annotations"), list):
        raise ValueError(f"{label} must contain an annotations list")


def _require_risk_annotation_manifest_artifact(
    *,
    artifacts_by_ref: Mapping[str, BundleArtifact],
    ref: object,
    table_name: str,
    label: str,
) -> None:
    if not isinstance(ref, str) or not ref.endswith(".json"):
        raise ValueError(f"{label} must reference a .json risk annotation manifest")
    artifact = _require_artifact(artifacts_by_ref=artifacts_by_ref, ref=ref, label=label)
    payload = _require_json_artifact_payload(artifact, label)
    if payload.get("schema_version") != RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION:
        raise ValueError(f"{label} must use {RISK_ANNOTATION_ARTIFACT_CONTRACT_VERSION}")
    if payload.get("artifact_kind") != "risk-annotations":
        raise ValueError(f"{label} must be a risk annotation manifest")
    if payload.get("table_name") != table_name:
        raise ValueError(f"{label} table_name does not match {table_name}")
    if not isinstance(payload.get("annotation_count"), int):
        raise ValueError(f"{label} must contain annotation_count")


def _require_json_artifact_payload(
    artifact: BundleArtifact,
    label: str,
) -> Mapping[str, Any]:
    if artifact.json_payload is None:
        raise ValueError(f"{label} must be provided as a JSON bundle artifact")
    return artifact.json_payload


def _ensure_bundle_artifact_ref(ref: str) -> None:
    ensure_bundle_relative_path(ref, "relative_ref")
    if ref.startswith(("cache://", "repo-object://")):
        raise ValueError("relative_ref must not use cache or repository-internal schemes")


def _write_bundle_artifacts(
    *,
    bundle_root: Path,
    refs: UploadPreviewBundleRefs,
    artifacts: tuple[BundleArtifact, ...],
) -> None:
    artifact_by_ref = {
        artifact.relative_ref: artifact
        for artifact in (
            *_directory_manifest_artifacts(refs),
            *artifacts,
        )
    }
    for relative_ref in sorted(artifact_by_ref):
        _write_bundle_artifact(bundle_root, artifact_by_ref[relative_ref])


def _directory_manifest_artifacts(
    refs: UploadPreviewBundleRefs,
) -> tuple[BundleArtifact, ...]:
    directory_refs = {
        ref
        for ref in (
            refs.base_tables_ref,
            refs.current_tables_ref,
            refs.before_fallback_tables_ref,
            refs.diff_artifacts_ref,
            refs.risk_artifacts_ref,
            refs.derived_artifacts_ref,
        )
        if _is_directory_ref(ref)
    }
    return tuple(
        BundleArtifact.json(
            _join_ref(directory_ref, "_manifest.json"),
            {
                "schema_version": "upload-preview-bundle-directory-manifest/v1",
                "directory_ref": directory_ref,
                "compatibility_note": "adapter-populated directory root",
            },
        )
        for directory_ref in sorted(directory_refs)
    )


def _is_directory_ref(ref: str | None) -> bool:
    return isinstance(ref, str) and bool(ref) and ref.endswith("/")


def _join_ref(directory_ref: str, filename: str) -> str:
    return f"{directory_ref.rstrip('/')}/{filename}"


def _write_bundle_artifact(bundle_root: Path, artifact: BundleArtifact) -> None:
    pure_path = PurePosixPath(artifact.relative_ref)
    path = bundle_root.joinpath(*pure_path.parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if artifact.json_payload is not None:
        path.write_text(
            json.dumps(artifact.json_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return
    if artifact.content_bytes is None:
        source_path = artifact.source_path
        if source_path is None:
            raise RuntimeError("artifact content is unexpectedly empty")
        if source_path.resolve() == path.resolve():
            return
        temp_path = path.with_name(f"{path.name}.tmp")
        copyfile(source_path, temp_path)
        temp_path.replace(path)
        return
    path.write_bytes(artifact.content_bytes)


def _preview_result(
    sidecar_result: CoreBundleAssemblyResult,
    tarball: TarballMetadata | None,
    *,
    bundle_write_duration_ms: int | None = None,
    tar_create_duration_ms: int | None = None,
) -> UploadPreviewBundleResult:
    return UploadPreviewBundleResult(
        bundle_root=sidecar_result.bundle_root,
        manifest_path=sidecar_result.manifest_path,
        preview_index_path=sidecar_result.preview_index_path,
        alignment_report_path=sidecar_result.alignment_report_path,
        comparison_surface_path=sidecar_result.comparison_surface_path,
        diff_summary_path=sidecar_result.diff_summary_path,
        risk_report_path=sidecar_result.risk_report_path,
        strategy_manifest_path=sidecar_result.strategy_manifest_path,
        derived_artifact_paths=sidecar_result.derived_artifact_paths,
        manifest=sidecar_result.manifest,
        preview_index=sidecar_result.preview_index,
        tarball=tarball,
        bundle_write_duration_ms=bundle_write_duration_ms,
        tar_create_duration_ms=tar_create_duration_ms,
    )


__all__ = [
    "BundleArtifact",
    "UploadPreviewBundleAssembler",
    "UploadPreviewBundlePayloadInput",
    "UploadPreviewBundleRefs",
    "UploadPreviewBundleRequest",
    "UploadPreviewBundleResult",
    "build_upload_preview_bundle_request",
]
