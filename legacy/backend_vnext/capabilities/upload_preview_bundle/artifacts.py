from __future__ import annotations

from pathlib import Path, PurePosixPath
from shutil import copyfile

from ...artifacts import RecordsArtifact
from ..business_projection import BusinessProjectionResult
from ..risk_evaluation import RiskAnnotationArtifact
from ..surface_assembly import ComparisonSurface
from .assembler import BundleArtifact


def comparison_records_bundle_artifacts(
    *,
    surface: ComparisonSurface,
    records_artifacts: tuple[RecordsArtifact, ...],
    bundle_root: Path,
) -> tuple[BundleArtifact, ...]:
    artifacts_by_table = {
        artifact.manifest.table_name: artifact
        for artifact in records_artifacts
    }
    bundle_artifacts: list[BundleArtifact] = []
    for table in surface.tables:
        records_ref = table.records_refs.records_ref
        if records_ref is None:
            continue
        artifact = artifacts_by_table.get(table.table_name)
        if artifact is None:
            raise RuntimeError(
                f"comparison records artifact is missing for preview table {table.table_name}"
            )
        records_path = bundle_artifact_path(bundle_root, records_ref)
        copy_file_atomic(artifact.content_path, records_path)
        bundle_artifacts.append(BundleArtifact.file(records_ref, records_path))
        manifest_ref = table.records_refs.records_manifest_ref
        if manifest_ref is not None:
            bundle_artifacts.append(
                BundleArtifact.json(manifest_ref, artifact.manifest.to_payload())
            )
    return tuple(bundle_artifacts)


def risk_annotation_bundle_artifacts(
    *,
    surface: ComparisonSurface,
    annotation_artifacts: tuple[RiskAnnotationArtifact, ...],
) -> tuple[BundleArtifact, ...]:
    artifacts_by_table = {
        artifact.table_name: artifact
        for artifact in annotation_artifacts
    }
    bundle_artifacts: list[BundleArtifact] = []
    for table in surface.tables:
        annotation_ref = table.risk_refs.annotation_ref
        annotation_manifest_ref = table.risk_refs.annotation_manifest_ref
        if annotation_ref is None and annotation_manifest_ref is None:
            continue
        artifact = artifacts_by_table.get(table.table_name)
        if artifact is None:
            raise RuntimeError(
                f"risk annotation artifact is missing for preview table {table.table_name}"
            )
        if annotation_ref is not None:
            bundle_artifacts.append(
                BundleArtifact.json(annotation_ref, artifact.content_payload())
            )
        if annotation_manifest_ref is not None:
            bundle_artifacts.append(
                BundleArtifact.json(annotation_manifest_ref, artifact.manifest_payload())
            )
    return tuple(bundle_artifacts)


def business_projection_bundle_artifacts(
    projection_result: BusinessProjectionResult | None,
    *,
    ref_prefix: str = "",
) -> tuple[BundleArtifact, ...]:
    if projection_result is None:
        return ()
    normalized_prefix = ref_prefix.strip("/")
    def scoped_ref(ref: str) -> str:
        return f"{normalized_prefix}/{ref}" if normalized_prefix else ref
    artifacts = [
        BundleArtifact.json(
            scoped_ref(f"projections/{projection.projection_id}.json"),
            projection.to_payload(),
        )
        for projection in projection_result.projections
    ]
    if projection_result.diagnostics:
        artifacts.append(
            BundleArtifact.json(
                scoped_ref("projections/diagnostics.json"),
                {
                    "diagnostics": [
                        diagnostic.to_payload()
                        for diagnostic in projection_result.diagnostics
                    ],
                },
            )
        )
    return tuple(artifacts)


def bundle_artifact_path(bundle_root: Path, relative_ref: str) -> Path:
    pure_path = PurePosixPath(relative_ref)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("bundle artifact ref must be relative")
    return bundle_root.joinpath(*pure_path.parts)


def copy_file_atomic(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.resolve() == target_path.resolve():
        return
    temporary_path = target_path.with_name(f"{target_path.name}.tmp")
    copyfile(source_path, temporary_path)
    temporary_path.replace(target_path)


__all__ = [
    "business_projection_bundle_artifacts",
    "bundle_artifact_path",
    "comparison_records_bundle_artifacts",
    "copy_file_atomic",
    "risk_annotation_bundle_artifacts",
]
