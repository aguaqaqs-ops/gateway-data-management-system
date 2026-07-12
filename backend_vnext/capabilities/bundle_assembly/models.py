from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..comparison.models import ComparisonFacts, ComparisonRecordsClosure, ComparisonTableFact, ComparisonTableStatus, ComparisonRole
from ..business_projection.models import BusinessProjectionResult
from ..risk_evaluation.aggregation import highest_risk_level
from ..risk_evaluation.models import RiskLevel, RiskReport, RiskTableRisk
from ..surface_assembly.models import ComparisonSurface, SurfaceSummary, SurfaceTable
from .digest import build_bundle_closure_digest, build_bundle_digest
from .versions import (
    COMPARISON_BUNDLE_ARTIFACT_CLOSURE_KIND,
    COMPARISON_BUNDLE_ARTIFACT_KIND,
    COMPARISON_BUNDLE_CONTRACT_VERSION,
    COMPARISON_BUNDLE_PROFILE_MULTI_PAIR,
    COMPARISON_BUNDLE_PROFILE_SINGLE_PAIR,
)


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(value)


def _normalize_str_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, tuple):
        values = tuple(values)
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError("tuple values must be non-empty strings")
        normalized.append(value)
    return tuple(normalized)


class BundleProfile(StrEnum):
    SINGLE_PAIR = COMPARISON_BUNDLE_PROFILE_SINGLE_PAIR
    MULTI_PAIR = COMPARISON_BUNDLE_PROFILE_MULTI_PAIR


@dataclass(frozen=True, slots=True)
class BundleInput:
    input_index: int
    role: ComparisonRole | str
    display_name: str | None = None
    display_metadata: Mapping[str, object] = field(default_factory=dict)
    snapshot_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_index, int) or isinstance(self.input_index, bool) or self.input_index < 0:
            raise ValueError("input_index must be a non-negative integer")
        object.__setattr__(self, "role", ComparisonRole(self.role))
        if self.display_name is not None and not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string or None")
        object.__setattr__(self, "display_metadata", _mapping_payload(self.display_metadata))
        if self.snapshot_digest is not None:
            object.__setattr__(self, "snapshot_digest", _optional_digest(self.snapshot_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "input_index": self.input_index,
            "role": self.role.value,
            "display_metadata": _mapping_payload(self.display_metadata),
        }
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        if self.snapshot_digest is not None:
            payload["snapshot_digest"] = self.snapshot_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        return self.payload_for_digest()


@dataclass(frozen=True, slots=True)
class BundlePairSummary(SurfaceSummary):
    pass


@dataclass(frozen=True, slots=True)
class BundlePairArtifactClosure:
    pair_id: str
    surface_digest: DigestRef | str
    surface_ref: str
    comparison_records_closure: ComparisonRecordsClosure | None = None
    risk_report: RiskReport | None = None
    business_projection_result: BusinessProjectionResult | None = None
    diagnostics_refs: tuple[str, ...] = field(default_factory=tuple)
    shared_artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        object.__setattr__(self, "surface_digest", _optional_digest(self.surface_digest))
        if not isinstance(self.surface_ref, str) or not self.surface_ref:
            raise ValueError("surface_ref must be a non-empty string")
        if self.comparison_records_closure is not None and not isinstance(self.comparison_records_closure, ComparisonRecordsClosure):
            raise TypeError("comparison_records_closure must be a ComparisonRecordsClosure or None")
        if self.risk_report is not None and not isinstance(self.risk_report, RiskReport):
            raise TypeError("risk_report must be a RiskReport or None")
        if self.business_projection_result is not None and not isinstance(self.business_projection_result, BusinessProjectionResult):
            raise TypeError("business_projection_result must be a BusinessProjectionResult or None")
        object.__setattr__(self, "diagnostics_refs", _normalize_str_tuple(self.diagnostics_refs))
        if not isinstance(self.shared_artifacts, tuple):
            object.__setattr__(self, "shared_artifacts", tuple(self.shared_artifacts))
        normalized_shared_artifacts: list[ArtifactRef] = []
        for artifact_ref in self.shared_artifacts:
            if not isinstance(artifact_ref, ArtifactRef):
                raise TypeError("shared_artifacts must contain ArtifactRef values")
            normalized_shared_artifacts.append(artifact_ref)
        object.__setattr__(self, "shared_artifacts", tuple(normalized_shared_artifacts))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "surface_digest": self.surface_digest.to_payload(),
        }
        if self.comparison_records_closure is not None:
            payload["comparison_records_closure_digest"] = self.comparison_records_closure.closure_manifest_digest.to_payload()
        if self.risk_report is not None:
            payload["risk_report_digest"] = _build_risk_report_digest(self.risk_report).to_payload()
        if self.business_projection_result is not None:
            payload["business_projection_digests"] = [
                projection.projection_digest.to_payload()
                for projection in self.business_projection_result.projections
            ]
        if self.shared_artifacts:
            payload["shared_artifact_manifest_digests"] = [
                artifact_ref.manifest_digest.to_payload() for artifact_ref in self.shared_artifacts
            ]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["pair_id"] = self.pair_id
        payload["surface_ref"] = self.surface_ref
        if self.comparison_records_closure is not None:
            payload["comparison_records_closure"] = self.comparison_records_closure.to_payload()
        if self.risk_report is not None:
            payload["risk_report"] = self.risk_report.to_payload()
        if self.business_projection_result is not None:
            payload["business_projections"] = [
                {
                    "projection_id": projection.projection_id,
                    "projection_kind": projection.projection_kind.value,
                    "projection_ref": f"projections/{projection.projection_id}.json",
                    "projection_digest": projection.projection_digest.to_payload(),
                }
                for projection in self.business_projection_result.projections
            ]
            payload["business_projection_summary"] = dict(self.business_projection_result.summary)
            if self.business_projection_result.diagnostics:
                payload["business_projection_diagnostics_ref"] = "projections/diagnostics.json"
        if self.diagnostics_refs:
            payload["diagnostics_refs"] = list(self.diagnostics_refs)
        if self.shared_artifacts:
            payload["shared_artifacts"] = [artifact_ref.to_payload() for artifact_ref in self.shared_artifacts]
        return payload


@dataclass(frozen=True, slots=True)
class BundlePair:
    pair_id: str
    before_input_index: int
    current_input_index: int
    surface_ref: str
    surface_digest: DigestRef | str
    comparison_digest: DigestRef | str
    risk_evaluation_digest: DigestRef | str | None = None
    summary: SurfaceSummary = field(default_factory=lambda: SurfaceSummary(table_count=0))

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        for field_name in ("before_input_index", "current_input_index"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.surface_ref, str) or not self.surface_ref:
            raise ValueError("surface_ref must be a non-empty string")
        object.__setattr__(self, "surface_digest", _optional_digest(self.surface_digest))
        object.__setattr__(self, "comparison_digest", _optional_digest(self.comparison_digest))
        if self.risk_evaluation_digest is not None:
            object.__setattr__(self, "risk_evaluation_digest", _optional_digest(self.risk_evaluation_digest))
        if not isinstance(self.summary, SurfaceSummary):
            raise TypeError("summary must be a SurfaceSummary")

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "before_input_index": self.before_input_index,
            "current_input_index": self.current_input_index,
            "surface_digest": self.surface_digest.to_payload(),
            "comparison_digest": self.comparison_digest.to_payload(),
            "summary": self.summary.payload_for_digest(),
        }
        if self.risk_evaluation_digest is not None:
            payload["risk_evaluation_digest"] = self.risk_evaluation_digest.to_payload()
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["pair_id"] = self.pair_id
        payload["surface_ref"] = self.surface_ref
        payload["summary"] = self.summary.to_payload()
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonBundleArtifactClosurePair:
    pair_id: str
    surface_digest: DigestRef | str
    comparison_records_closure_digest: DigestRef | str | None = None
    risk_report_digest: DigestRef | str | None = None
    business_projection_digests: tuple[DigestRef | str, ...] = field(default_factory=tuple)
    shared_artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        object.__setattr__(self, "surface_digest", _optional_digest(self.surface_digest))
        if self.comparison_records_closure_digest is not None:
            object.__setattr__(self, "comparison_records_closure_digest", _optional_digest(self.comparison_records_closure_digest))
        if self.risk_report_digest is not None:
            object.__setattr__(self, "risk_report_digest", _optional_digest(self.risk_report_digest))
        if not isinstance(self.business_projection_digests, tuple):
            object.__setattr__(self, "business_projection_digests", tuple(self.business_projection_digests))
        object.__setattr__(
            self,
            "business_projection_digests",
            tuple(_optional_digest(digest) for digest in self.business_projection_digests),
        )
        if not isinstance(self.shared_artifacts, tuple):
            object.__setattr__(self, "shared_artifacts", tuple(self.shared_artifacts))
        normalized_shared_artifacts: list[ArtifactRef] = []
        for artifact_ref in self.shared_artifacts:
            if not isinstance(artifact_ref, ArtifactRef):
                raise TypeError("shared_artifacts must contain ArtifactRef values")
            normalized_shared_artifacts.append(artifact_ref)
        object.__setattr__(self, "shared_artifacts", tuple(normalized_shared_artifacts))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "surface_digest": self.surface_digest.to_payload(),
        }
        if self.comparison_records_closure_digest is not None:
            payload["comparison_records_closure_digest"] = self.comparison_records_closure_digest.to_payload()
        if self.risk_report_digest is not None:
            payload["risk_report_digest"] = self.risk_report_digest.to_payload()
        if self.business_projection_digests:
            payload["business_projection_digests"] = [
                digest.to_payload()
                for digest in self.business_projection_digests
            ]
        if self.shared_artifacts:
            payload["shared_artifact_manifest_digests"] = [
                artifact_ref.manifest_digest.to_payload() for artifact_ref in self.shared_artifacts
            ]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["pair_id"] = self.pair_id
        if self.shared_artifacts:
            payload["shared_artifacts"] = [artifact_ref.to_payload() for artifact_ref in self.shared_artifacts]
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonBundleArtifactClosure:
    bundle_manifest_digest: DigestRef | str
    pairs: tuple[ComparisonBundleArtifactClosurePair, ...] = field(default_factory=tuple)
    shared_snapshot_artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    diagnostics_refs: tuple[str, ...] = field(default_factory=tuple)
    closure_manifest_digest: DigestRef | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_manifest_digest", _optional_digest(self.bundle_manifest_digest))
        if not isinstance(self.pairs, tuple):
            object.__setattr__(self, "pairs", tuple(self.pairs))
        normalized_pairs: list[ComparisonBundleArtifactClosurePair] = []
        for pair in self.pairs:
            if not isinstance(pair, ComparisonBundleArtifactClosurePair):
                raise TypeError("pairs must contain ComparisonBundleArtifactClosurePair values")
            normalized_pairs.append(pair)
        object.__setattr__(self, "pairs", tuple(normalized_pairs))
        if not isinstance(self.shared_snapshot_artifacts, tuple):
            object.__setattr__(self, "shared_snapshot_artifacts", tuple(self.shared_snapshot_artifacts))
        normalized_shared_artifacts: list[ArtifactRef] = []
        for artifact_ref in self.shared_snapshot_artifacts:
            if not isinstance(artifact_ref, ArtifactRef):
                raise TypeError("shared_snapshot_artifacts must contain ArtifactRef values")
            normalized_shared_artifacts.append(artifact_ref)
        object.__setattr__(self, "shared_snapshot_artifacts", tuple(normalized_shared_artifacts))
        object.__setattr__(self, "diagnostics_refs", _normalize_str_tuple(self.diagnostics_refs))
        if self.closure_manifest_digest is None:
            object.__setattr__(self, "closure_manifest_digest", build_bundle_closure_digest(self))
        else:
            object.__setattr__(self, "closure_manifest_digest", _optional_digest(self.closure_manifest_digest))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "bundle_manifest_digest": self.bundle_manifest_digest.to_payload(),
            "pairs": [pair.payload_for_digest() for pair in self.pairs],
        }
        if self.shared_snapshot_artifacts:
            payload["shared_snapshot_artifact_manifest_digests"] = [
                artifact_ref.manifest_digest.to_payload() for artifact_ref in self.shared_snapshot_artifacts
            ]
        return payload

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["closure_manifest_digest"] = self.closure_manifest_digest.to_payload() if self.closure_manifest_digest is not None else None
        payload["pairs"] = [pair.to_payload() for pair in self.pairs]
        if self.shared_snapshot_artifacts:
            payload["shared_snapshot_artifacts"] = [artifact_ref.to_payload() for artifact_ref in self.shared_snapshot_artifacts]
        if self.diagnostics_refs:
            payload["diagnostics_refs"] = list(self.diagnostics_refs)
        return payload


@dataclass(frozen=True, slots=True)
class BundleSummary:
    pair_count: int
    table_count: int
    changed_table_count: int = 0
    degraded_table_count: int = 0
    risk_level: RiskLevel | str | None = None
    diagnostics_count: int = 0

    def __post_init__(self) -> None:
        for field_name in ("pair_count", "table_count", "changed_table_count", "degraded_table_count", "diagnostics_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.risk_level is not None:
            object.__setattr__(self, "risk_level", RiskLevel(self.risk_level))

    def payload_for_digest(self) -> dict[str, object]:
        payload = {
            "pair_count": self.pair_count,
            "table_count": self.table_count,
            "changed_table_count": self.changed_table_count,
            "degraded_table_count": self.degraded_table_count,
            "diagnostics_count": self.diagnostics_count,
        }
        if self.risk_level is not None:
            payload["risk_level"] = self.risk_level.value
        return payload

    def to_payload(self) -> dict[str, object]:
        return self.payload_for_digest()


@dataclass(frozen=True, slots=True)
class ComparisonBundle:
    bundle_contract_version: str = COMPARISON_BUNDLE_CONTRACT_VERSION
    bundle_digest: DigestRef | str | None = None
    bundle_profile: BundleProfile | str = BundleProfile.SINGLE_PAIR
    inputs: tuple[BundleInput, ...] = field(default_factory=tuple)
    pairs: tuple[BundlePair, ...] = field(default_factory=tuple)
    summary: BundleSummary = field(default_factory=lambda: BundleSummary(pair_count=0, table_count=0))
    artifact_closure_ref: str = "artifact-closure.json"
    artifact_closure_manifest_digest: DigestRef | str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.bundle_contract_version, str) or not self.bundle_contract_version:
            raise ValueError("bundle_contract_version must be a non-empty string")
        object.__setattr__(self, "bundle_profile", BundleProfile(self.bundle_profile))
        if not isinstance(self.inputs, tuple):
            object.__setattr__(self, "inputs", tuple(self.inputs))
        normalized_inputs: list[BundleInput] = []
        for bundle_input in self.inputs:
            if not isinstance(bundle_input, BundleInput):
                raise TypeError("inputs must contain BundleInput values")
            normalized_inputs.append(bundle_input)
        object.__setattr__(self, "inputs", tuple(normalized_inputs))
        if not isinstance(self.pairs, tuple):
            object.__setattr__(self, "pairs", tuple(self.pairs))
        normalized_pairs: list[BundlePair] = []
        for pair in self.pairs:
            if not isinstance(pair, BundlePair):
                raise TypeError("pairs must contain BundlePair values")
            normalized_pairs.append(pair)
        object.__setattr__(self, "pairs", tuple(normalized_pairs))
        if not isinstance(self.summary, BundleSummary):
            raise TypeError("summary must be a BundleSummary")
        if not isinstance(self.artifact_closure_ref, str) or not self.artifact_closure_ref:
            raise ValueError("artifact_closure_ref must be a non-empty string")
        if self.artifact_closure_manifest_digest is None:
            raise ValueError("artifact_closure_manifest_digest is required for bundle digest")
        object.__setattr__(self, "artifact_closure_manifest_digest", _optional_digest(self.artifact_closure_manifest_digest))
        if self.bundle_digest is None:
            object.__setattr__(self, "bundle_digest", build_bundle_digest(self))
        else:
            object.__setattr__(self, "bundle_digest", _optional_digest(self.bundle_digest))
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def payload_for_digest(self) -> dict[str, object]:
        return {
            "bundle_contract_version": self.bundle_contract_version,
            "bundle_profile": self.bundle_profile.value,
            "inputs": [bundle_input.payload_for_digest() for bundle_input in self.inputs],
            "pairs": [pair.payload_for_digest() for pair in self.pairs],
            "summary": self.summary.payload_for_digest(),
        }

    def to_payload(self) -> dict[str, object]:
        payload = self.payload_for_digest()
        payload["bundle_digest"] = self.bundle_digest.to_payload() if self.bundle_digest is not None else None
        payload["bundle_contract_version"] = self.bundle_contract_version
        payload["bundle_profile"] = self.bundle_profile.value
        payload["inputs"] = [bundle_input.to_payload() for bundle_input in self.inputs]
        payload["pairs"] = [pair.to_payload() for pair in self.pairs]
        payload["summary"] = self.summary.to_payload()
        payload["artifact_closure_ref"] = self.artifact_closure_ref
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload


@dataclass(frozen=True, slots=True)
class BundlePairAssemblyInput:
    pair_id: str
    before_input_index: int
    current_input_index: int
    comparison_surface: ComparisonSurface
    surface_artifact_closure: BundlePairArtifactClosure

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        for field_name in ("before_input_index", "current_input_index"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.comparison_surface, ComparisonSurface):
            raise TypeError("comparison_surface must be a ComparisonSurface")
        if not isinstance(self.surface_artifact_closure, BundlePairArtifactClosure):
            raise TypeError("surface_artifact_closure must be a BundlePairArtifactClosure")


@dataclass(frozen=True, slots=True)
class BundleAssemblyInput:
    bundle_root: object
    bundle_contract_version: str = COMPARISON_BUNDLE_CONTRACT_VERSION
    bundle_profile: BundleProfile | str = BundleProfile.SINGLE_PAIR
    inputs: tuple[BundleInput, ...] = field(default_factory=tuple)
    pairs: tuple[BundlePairAssemblyInput, ...] = field(default_factory=tuple)
    shared_artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)
    artifact_policy: str = "DEFAULT"
    ref_scope: str = "BUNDLE_RELATIVE"

    def __post_init__(self) -> None:
        from pathlib import Path

        if not isinstance(self.bundle_root, Path):
            raise TypeError("bundle_root must be a Path")
        if not isinstance(self.bundle_contract_version, str) or not self.bundle_contract_version:
            raise ValueError("bundle_contract_version must be a non-empty string")
        object.__setattr__(self, "bundle_profile", BundleProfile(self.bundle_profile))
        if not isinstance(self.inputs, tuple):
            object.__setattr__(self, "inputs", tuple(self.inputs))
        normalized_inputs: list[BundleInput] = []
        for bundle_input in self.inputs:
            if not isinstance(bundle_input, BundleInput):
                raise TypeError("inputs must contain BundleInput values")
            normalized_inputs.append(bundle_input)
        object.__setattr__(self, "inputs", tuple(normalized_inputs))
        if not isinstance(self.pairs, tuple):
            object.__setattr__(self, "pairs", tuple(self.pairs))
        normalized_pairs: list[BundlePairAssemblyInput] = []
        for pair in self.pairs:
            if not isinstance(pair, BundlePairAssemblyInput):
                raise TypeError("pairs must contain BundlePairAssemblyInput values")
            normalized_pairs.append(pair)
        object.__setattr__(self, "pairs", tuple(normalized_pairs))
        if not isinstance(self.shared_artifacts, tuple):
            object.__setattr__(self, "shared_artifacts", tuple(self.shared_artifacts))
        normalized_shared_artifacts: list[ArtifactRef] = []
        for artifact_ref in self.shared_artifacts:
            if not isinstance(artifact_ref, ArtifactRef):
                raise TypeError("shared_artifacts must contain ArtifactRef values")
            normalized_shared_artifacts.append(artifact_ref)
        object.__setattr__(self, "shared_artifacts", tuple(normalized_shared_artifacts))
        if not isinstance(self.artifact_policy, str) or not self.artifact_policy:
            raise ValueError("artifact_policy must be a non-empty string")
        if not isinstance(self.ref_scope, str) or self.ref_scope != "BUNDLE_RELATIVE":
            raise ValueError("ref_scope must be BUNDLE_RELATIVE in the first bundle version")


@dataclass(frozen=True, slots=True)
class BundleAssemblyResult:
    bundle_root: object
    manifest_path: object
    artifact_closure_path: object
    bundle_artifact_ref: ArtifactRef
    manifest: ComparisonBundle
    artifact_closure_manifest: ComparisonBundleArtifactClosure
    pair_paths: Mapping[str, object]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        from pathlib import Path

        if not isinstance(self.bundle_root, Path):
            raise TypeError("bundle_root must be a Path")
        if not isinstance(self.manifest_path, Path):
            raise TypeError("manifest_path must be a Path")
        if not isinstance(self.artifact_closure_path, Path):
            raise TypeError("artifact_closure_path must be a Path")
        if not isinstance(self.bundle_artifact_ref, ArtifactRef):
            raise TypeError("bundle_artifact_ref must be an ArtifactRef")
        if not isinstance(self.manifest, ComparisonBundle):
            raise TypeError("manifest must be a ComparisonBundle")
        if not isinstance(self.artifact_closure_manifest, ComparisonBundleArtifactClosure):
            raise TypeError("artifact_closure_manifest must be a ComparisonBundleArtifactClosure")
        if not isinstance(self.pair_paths, Mapping):
            raise TypeError("pair_paths must be a mapping")
        if not isinstance(self.diagnostics, tuple):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


def _risk_report_payload_for_digest(risk_report: RiskReport) -> dict[str, object]:
    return {
        "risk_report_contract_version": risk_report.risk_report_contract_version,
        "risk_evaluation_digest": risk_report.risk_evaluation_digest.to_payload(),
        "overall": risk_report.overall.to_payload(),
        "tables": [table.payload_for_digest() for table in risk_report.tables],
        "annotation_manifest_digests": [annotation_ref.manifest_digest.to_payload() for annotation_ref in risk_report.annotation_refs],
        "diagnostics": [diagnostic.to_payload() for diagnostic in risk_report.diagnostics],
    }


__all__ = [
    "BundleAssemblyInput",
    "BundleAssemblyResult",
    "BundleInput",
    "BundlePair",
    "BundlePairArtifactClosure",
    "BundlePairAssemblyInput",
    "BundlePairSummary",
    "BundleProfile",
    "BundleSummary",
    "ComparisonBundle",
    "ComparisonBundleArtifactClosure",
    "ComparisonBundleArtifactClosurePair",
]
