from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ...core.validation import ensure_bundle_relative_path, require_non_empty


BUNDLE_ASSEMBLY_VERSION = "preview-bundle/v2"
BUNDLE_ASSEMBLY_INDEX_VERSION = "preview-index/v2"


@dataclass(frozen=True)
class BundleRefs:
    manifest_ref: str = "manifest.json"
    strategy_manifest_ref: str = "preview_strategy_manifest.json"
    preview_index_ref: str = "preview_index.json"
    alignment_report_ref: str = "alignment_report.json"
    comparison_surface_ref: str = "comparison_surface.json"
    diff_summary_ref: str = "diff_summary.json"
    risk_report_ref: str = "risk_report.json"
    base_tables_ref: str = "snapshots/"
    current_tables_ref: str = "snapshots/"
    before_fallback_tables_ref: str = "snapshots/"
    diff_artifacts_ref: str = "pairs/"
    risk_artifacts_ref: str = "pairs/"
    derived_artifacts_ref: str = "derived/"
    bundle_relative_root: str = "."

    def __post_init__(self) -> None:
        for field_name in (
            "manifest_ref",
            "strategy_manifest_ref",
            "preview_index_ref",
            "alignment_report_ref",
            "comparison_surface_ref",
            "diff_summary_ref",
            "risk_report_ref",
            "base_tables_ref",
            "current_tables_ref",
            "before_fallback_tables_ref",
            "diff_artifacts_ref",
            "risk_artifacts_ref",
            "derived_artifacts_ref",
            "bundle_relative_root",
        ):
            ensure_bundle_relative_path(
                str(getattr(self, field_name)),
                field_name,
            )


@dataclass(frozen=True)
class BundleAssemblyRequest:
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
    refs: BundleRefs = field(default_factory=BundleRefs)
    derived_artifacts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    table_aliases: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_non_empty(self.preview_bundle_id, "preview_bundle_id")
        require_non_empty(self.preview_revision_id, "preview_revision_id")
        require_non_empty(
            self.preview_strategy_manifest_digest,
            "preview_strategy_manifest_digest",
        )
        require_non_empty(self.workspace_id, "workspace_id")
        require_non_empty(self.baseline_alignment, "baseline_alignment")
        require_non_empty(self.default_view_id, "default_view_id")
        require_non_empty(self.generated_at, "generated_at")
        for ref in self.derived_artifacts:
            ensure_bundle_relative_path(str(ref), "derived_artifacts ref")
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        for alias in self.table_aliases:
            if not isinstance(alias, Mapping):
                raise TypeError("table_aliases must contain mapping values")


@dataclass(frozen=True)
class BundleAssemblyResult:
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


class BundleAssembler:
    def index_payload(
        self,
        request: BundleAssemblyRequest,
    ) -> dict[str, Any]:
        return self._index_payload(request)

    def assemble(
        self,
        request: BundleAssemblyRequest,
    ) -> BundleAssemblyResult:
        request.bundle_root.mkdir(parents=True, exist_ok=True)
        manifest = self._manifest_payload(request)
        preview_index = self.index_payload(request)
        refs = request.refs

        root_payloads: tuple[tuple[str, Mapping[str, Any]], ...] = (
            (refs.manifest_ref, manifest),
            (refs.strategy_manifest_ref, request.preview_strategy_manifest),
            (refs.alignment_report_ref, request.alignment_report),
            (refs.preview_index_ref, preview_index),
            (refs.comparison_surface_ref, request.comparison_surface),
            (refs.diff_summary_ref, request.diff_summary),
            (refs.risk_report_ref, request.risk_report),
        )
        for ref, payload in root_payloads:
            self._write_json(self.bundle_file_path(request.bundle_root, ref), payload)

        derived_paths: dict[str, Path] = {}
        for ref, payload in request.derived_artifacts.items():
            path = self.bundle_file_path(request.bundle_root, str(ref))
            self._write_json(path, payload)
            derived_paths[str(ref)] = path

        return BundleAssemblyResult(
            bundle_root=request.bundle_root,
            manifest_path=self.bundle_file_path(request.bundle_root, refs.manifest_ref),
            preview_index_path=self.bundle_file_path(
                request.bundle_root,
                refs.preview_index_ref,
            ),
            alignment_report_path=self.bundle_file_path(
                request.bundle_root,
                refs.alignment_report_ref,
            ),
            comparison_surface_path=self.bundle_file_path(
                request.bundle_root,
                refs.comparison_surface_ref,
            ),
            diff_summary_path=self.bundle_file_path(
                request.bundle_root,
                refs.diff_summary_ref,
            ),
            risk_report_path=self.bundle_file_path(
                request.bundle_root,
                refs.risk_report_ref,
            ),
            strategy_manifest_path=self.bundle_file_path(
                request.bundle_root,
                refs.strategy_manifest_ref,
            ),
            derived_artifact_paths=derived_paths,
            manifest=manifest,
            preview_index=preview_index,
        )

    @staticmethod
    def bundle_file_path(bundle_root: Path, relative_ref: str) -> Path:
        ensure_bundle_relative_path(relative_ref, "relative_ref")
        pure_path = PurePosixPath(relative_ref)
        return bundle_root.joinpath(*pure_path.parts)

    @staticmethod
    def _manifest_payload(
        request: BundleAssemblyRequest,
    ) -> dict[str, Any]:
        refs = request.refs
        return {
            "schema_version": BUNDLE_ASSEMBLY_VERSION,
            "preview_bundle_id": request.preview_bundle_id,
            "preview_revision_id": request.preview_revision_id,
            "preview_strategy_manifest_ref": refs.strategy_manifest_ref,
            "preview_strategy_manifest_digest": (
                request.preview_strategy_manifest_digest
            ),
            "preview_index_ref": refs.preview_index_ref,
            "alignment_report_ref": refs.alignment_report_ref,
            "comparison_surface_ref": refs.comparison_surface_ref,
            "diff_summary_ref": refs.diff_summary_ref,
            "risk_report_ref": refs.risk_report_ref,
            "base_tables_ref": refs.base_tables_ref,
            "current_tables_ref": refs.current_tables_ref,
            "before_fallback_tables_ref": refs.before_fallback_tables_ref,
            "diff_artifacts_ref": refs.diff_artifacts_ref,
            "risk_artifacts_ref": refs.risk_artifacts_ref,
            "derived_artifacts_ref": refs.derived_artifacts_ref,
            "generated_at": request.generated_at,
        }

    @staticmethod
    def _index_payload(
        request: BundleAssemblyRequest,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": BUNDLE_ASSEMBLY_INDEX_VERSION,
            "preview_bundle_id": request.preview_bundle_id,
            "preview_revision_id": request.preview_revision_id,
            "preview_strategy_manifest_digest": (
                request.preview_strategy_manifest_digest
            ),
            "workspace_id": request.workspace_id,
            "baseline_alignment": request.baseline_alignment,
            "alignment_report": dict(request.alignment_report),
            "default_view_id": request.default_view_id,
            "views": [dict(view) for view in request.views],
            "tables": [dict(table) for table in request.tables],
            "sidebar_trees": [dict(tree) for tree in request.sidebar_trees],
            "generated_at": request.generated_at,
            "bundle_relative_root": request.refs.bundle_relative_root,
        }
        if request.table_aliases:
            payload["table_aliases"] = [dict(alias) for alias in request.table_aliases]
        return payload

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
__all__ = [
    "BUNDLE_ASSEMBLY_INDEX_VERSION",
    "BUNDLE_ASSEMBLY_VERSION",
    "BundleAssemblyRequest",
    "BundleAssemblyResult",
    "BundleAssembler",
    "BundleRefs",
]
