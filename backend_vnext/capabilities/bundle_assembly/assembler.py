from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from ...artifacts.manifest import ArtifactManifest, ArtifactRef
from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ..surface_assembly import ComparisonSurface
from ..risk_evaluation.aggregation import highest_risk_level
from .digest import build_bundle_closure_digest, build_bundle_digest
from .models import (
    BundleAssemblyInput,
    BundleAssemblyResult,
    BundleInput,
    BundlePair,
    BundlePairArtifactClosure,
    BundlePairAssemblyInput,
    BundleSummary,
    BundleProfile,
    ComparisonBundle,
    ComparisonBundleArtifactClosure,
    ComparisonBundleArtifactClosurePair,
    SurfaceSummary,
)
from .ref_rewrite import rewrite_surface_for_bundle
from .versions import (
    COMPARISON_BUNDLE_ARTIFACT_CLOSURE_KIND,
    COMPARISON_BUNDLE_ARTIFACT_KIND,
    COMPARISON_BUNDLE_CONTRACT_VERSION,
)


class BundleAssembler:
    def assemble(self, request: BundleAssemblyInput) -> BundleAssemblyResult:
        request.bundle_root.mkdir(parents=True, exist_ok=True)
        pair_outputs: list[BundlePair] = []
        pair_closure_outputs: list[ComparisonBundleArtifactClosurePair] = []
        pair_paths: dict[str, Path] = {}
        diagnostics: list[DiagnosticRecord] = []

        for pair in request.pairs:
            pair_path = request.bundle_root / "pairs" / pair.pair_id
            pair_path.mkdir(parents=True, exist_ok=True)
            rewritten_surface = rewrite_surface_for_bundle(pair.comparison_surface, pair.pair_id)
            pair_output = BundlePair(
                pair_id=pair.pair_id,
                before_input_index=pair.before_input_index,
                current_input_index=pair.current_input_index,
                surface_ref=f"pairs/{pair.pair_id}/comparison-surface.json",
                surface_digest=rewritten_surface.surface_digest,
                comparison_digest=rewritten_surface.comparison_digest,
                risk_evaluation_digest=rewritten_surface.risk_evaluation_digest,
                summary=SurfaceSummary(
                    table_count=rewritten_surface.summary.table_count,
                    changed_table_count=rewritten_surface.summary.changed_table_count,
                    degraded_table_count=rewritten_surface.summary.degraded_table_count,
                    risk_level=rewritten_surface.summary.risk_level,
                    diagnostics_count=rewritten_surface.summary.diagnostics_count,
                ),
            )
            pair_outputs.append(pair_output)
            pair_paths[pair.pair_id] = pair_path
            _write_json(pair_path / "comparison-surface.json", rewritten_surface.to_payload())
            if pair.surface_artifact_closure.comparison_records_closure is not None:
                _write_json(
                    pair_path / "comparison" / "records-closure.json",
                    pair.surface_artifact_closure.comparison_records_closure.to_payload(),
                )
            if pair.surface_artifact_closure.risk_report is not None:
                _write_json(
                    pair_path / "risk" / "risk-report.json",
                    pair.surface_artifact_closure.risk_report.to_payload(),
                )
                _write_json(
                    pair_path / "risk" / "risk-annotation-closure.json",
                    {
                        "annotation_refs": [
                            annotation_ref.to_payload()
                            for annotation_ref in pair.surface_artifact_closure.risk_report.annotation_refs
                        ]
                    },
                )
            if pair.surface_artifact_closure.business_projection_result is not None:
                projection_result = pair.surface_artifact_closure.business_projection_result
                for projection in projection_result.projections:
                    _write_json(
                        pair_path / "projections" / f"{projection.projection_id}.json",
                        projection.to_payload(),
                    )
                if projection_result.diagnostics:
                    _write_json(
                        pair_path / "projections" / "diagnostics.json",
                        {
                            "diagnostics": [
                                diagnostic.to_payload()
                                for diagnostic in projection_result.diagnostics
                            ]
                        },
                    )
            if pair.surface_artifact_closure.diagnostics_refs:
                _write_json(
                    pair_path / "diagnostics" / "diagnostics.json",
                    {"diagnostics_refs": list(pair.surface_artifact_closure.diagnostics_refs)},
                )
            pair_closure_outputs.append(
                ComparisonBundleArtifactClosurePair(
                    pair_id=pair.pair_id,
                    surface_digest=rewritten_surface.surface_digest,
                    comparison_records_closure_digest=(
                        pair.surface_artifact_closure.comparison_records_closure.closure_manifest_digest
                        if pair.surface_artifact_closure.comparison_records_closure is not None
                        else None
                    ),
                    risk_report_digest=(
                        _risk_report_digest(pair.surface_artifact_closure.risk_report)
                        if pair.surface_artifact_closure.risk_report is not None
                        else None
                    ),
                    business_projection_digests=(
                        ()
                        if pair.surface_artifact_closure.business_projection_result is None
                        else tuple(
                            projection.projection_digest
                            for projection in pair.surface_artifact_closure.business_projection_result.projections
                        )
                    ),
                    shared_artifacts=pair.surface_artifact_closure.shared_artifacts,
                )
            )

        bundle_summary = BundleSummary(
            pair_count=len(pair_outputs),
            table_count=sum(pair.summary.table_count for pair in pair_outputs),
            changed_table_count=sum(pair.summary.changed_table_count for pair in pair_outputs),
            degraded_table_count=sum(pair.summary.degraded_table_count for pair in pair_outputs),
            risk_level=_bundle_risk_level(pair_outputs),
            diagnostics_count=len(diagnostics),
        )
        bundle_inputs = tuple(request.inputs)
        bundle_manifest_without_closure = ComparisonBundle(
            bundle_contract_version=request.bundle_contract_version,
            bundle_profile=request.bundle_profile,
            inputs=bundle_inputs,
            pairs=tuple(pair_outputs),
            summary=bundle_summary,
            artifact_closure_ref="artifact-closure.json",
            artifact_closure_manifest_digest=DigestRef.from_hex("0" * 64),
            diagnostics=tuple(diagnostics),
        )
        bundle_manifest_digest = DigestRef.from_payload(bundle_manifest_without_closure.payload_for_digest())
        artifact_closure_manifest = ComparisonBundleArtifactClosure(
            bundle_manifest_digest=bundle_manifest_digest,
            pairs=tuple(pair_closure_outputs),
            shared_snapshot_artifacts=tuple(request.shared_artifacts),
            diagnostics_refs=(),
        )
        bundle_manifest = ComparisonBundle(
            bundle_contract_version=request.bundle_contract_version,
            bundle_profile=request.bundle_profile,
            inputs=bundle_inputs,
            pairs=tuple(pair_outputs),
            summary=bundle_summary,
            artifact_closure_ref="artifact-closure.json",
            artifact_closure_manifest_digest=artifact_closure_manifest.closure_manifest_digest,
            diagnostics=tuple(diagnostics),
        )
        manifest_payload = bundle_manifest.to_payload()
        closure_payload = artifact_closure_manifest.to_payload()
        manifest_path = request.bundle_root / "manifest.json"
        artifact_closure_path = request.bundle_root / "artifact-closure.json"
        _write_json(manifest_path, manifest_payload)
        _write_json(artifact_closure_path, closure_payload)
        for bundle_input in bundle_inputs:
            _write_json(request.bundle_root / "inputs" / f"input-{bundle_input.input_index}.json", bundle_input.to_payload())
        bundle_content_bytes = canonical_json_bytes(manifest_payload)
        bundle_manifest_artifact = ArtifactManifest(
            artifact_kind=COMPARISON_BUNDLE_ARTIFACT_KIND,
            artifact_contract_version=request.bundle_contract_version,
            content_digest=DigestRef.from_bytes(bundle_content_bytes),
            content_size_bytes=len(bundle_content_bytes),
            metadata={
                "bundle_digest": bundle_manifest.bundle_digest.to_payload() if bundle_manifest.bundle_digest is not None else None,
                "bundle_profile": bundle_manifest.bundle_profile.value,
            },
            diagnostics=tuple(diagnostics),
        )
        bundle_artifact_ref = bundle_manifest_artifact.to_ref(DigestRef.from_payload(bundle_manifest_artifact.to_payload()))
        return BundleAssemblyResult(
            bundle_root=request.bundle_root,
            manifest_path=manifest_path,
            artifact_closure_path=artifact_closure_path,
            bundle_artifact_ref=bundle_artifact_ref,
            manifest=bundle_manifest,
            artifact_closure_manifest=artifact_closure_manifest,
            pair_paths=pair_paths,
            diagnostics=tuple(diagnostics),
        )


def _bundle_risk_level(pairs: list[BundlePair]) -> object:
    levels = [pair.summary.risk_level for pair in pairs]
    return highest_risk_level(levels)


def _risk_report_digest(risk_report: object) -> DigestRef:
    payload = {
        "risk_report_contract_version": risk_report.risk_report_contract_version,
        "risk_evaluation_digest": risk_report.risk_evaluation_digest.to_payload(),
        "overall": risk_report.overall.to_payload(),
        "tables": [table.payload_for_digest() for table in risk_report.tables],
        "annotation_manifest_digests": [annotation_ref.manifest_digest.to_payload() for annotation_ref in risk_report.annotation_refs],
        "diagnostics": [diagnostic.to_payload() for diagnostic in risk_report.diagnostics],
    }
    return DigestRef.from_payload(payload)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
