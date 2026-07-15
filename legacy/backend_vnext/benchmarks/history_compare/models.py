from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ...core import DigestRef, DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..flow_journey.models import FlowJourneyBenchmarkStageResult
from ..repository_import import (
    RepositoryImportBenchmarkDatasetManifest,
    RepositoryImportBenchmarkMachineProfile,
)
from ...capabilities.repository_import import RepositoryImportProvider


class HistoryCompareBenchmarkProfile(StrEnum):
    REPO_BACKED_WARM = "REPO_BACKED_WARM"
    REPO_BACKED_WARM_PARTIAL = "REPO_BACKED_WARM_PARTIAL"
    REPO_BACKED_COLD = "REPO_BACKED_COLD"
    REPO_BACKED_WARM_VERIFICATION = "REPO_BACKED_WARM_VERIFICATION"


class HistoryCompareBenchmarkStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


HistoryCompareBenchmarkStageResult = FlowJourneyBenchmarkStageResult


def _payload_value(value: object) -> object:
    if value is None:
        return None
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _payload_value(to_payload())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _payload_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    if isinstance(value, set):
        return [_payload_value(item) for item in sorted(value, key=str)]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer or None")
    return value


@dataclass(frozen=True, slots=True)
class HistoryCompareRepositoryBackedDatasetInput:
    dataset_id: str
    before_repository_path: Path
    current_repository_path: Path
    before_repository_ref: str
    current_repository_ref: str
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    repository_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id:
            raise ValueError("dataset_id must be a non-empty string")
        for field_name in ("before_repository_path", "current_repository_path"):
            value = getattr(self, field_name)
            if not isinstance(value, Path):
                raise TypeError(f"{field_name} must be a Path")
        for field_name in ("before_repository_ref", "current_repository_ref"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        normalized_requested_tables: list[str] = []
        seen_requested_tables: set[str] = set()
        for table_name in self.requested_tables:
            canonical_table = str(table_name).strip()
            if not canonical_table:
                continue
            canonical_table = canonical_identifier(canonical_table)
            if canonical_table in seen_requested_tables:
                continue
            seen_requested_tables.add(canonical_table)
            normalized_requested_tables.append(canonical_table)
        object.__setattr__(self, "requested_tables", tuple(normalized_requested_tables))
        if self.repository_id is None:
            object.__setattr__(self, "repository_id", self.dataset_id)
        elif not isinstance(self.repository_id, str) or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string or None")

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "before_repository_path": str(self.before_repository_path),
            "current_repository_path": str(self.current_repository_path),
            "before_repository_ref": self.before_repository_ref,
            "current_repository_ref": self.current_repository_ref,
            "requested_tables": list(self.requested_tables),
            "repository_id": self.repository_id,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "HistoryCompareRepositoryBackedDatasetInput":
        requested_tables = payload.get("requested_tables", ())
        if requested_tables is None:
            requested_tables = ()
        if not isinstance(requested_tables, Sequence):
            raise TypeError("requested_tables payload must be a sequence")
        before_repository_path = payload.get("before_repository_path")
        current_repository_path = payload.get("current_repository_path")
        if before_repository_path is None or current_repository_path is None:
            raise TypeError(
                "repository-backed input payload must include both before_repository_path and current_repository_path"
            )
        return cls(
            dataset_id=_required_str(payload, "dataset_id"),
            before_repository_path=Path(_required_str({"before_repository_path": before_repository_path}, "before_repository_path")),
            current_repository_path=Path(_required_str({"current_repository_path": current_repository_path}, "current_repository_path")),
            before_repository_ref=_required_str(payload, "before_repository_ref"),
            current_repository_ref=_required_str(payload, "current_repository_ref"),
            requested_tables=tuple(str(item) for item in requested_tables),
            repository_id=_optional_str(payload.get("repository_id"), field_name="repository_id"),
        )


@dataclass(frozen=True, slots=True)
class HistoryCompareBenchmarkResult:
    dataset_id: str
    dataset_kind: str
    profile: HistoryCompareBenchmarkProfile | str
    provider: RepositoryImportProvider | str
    status: HistoryCompareBenchmarkStatus | str
    source_sql_digest: DigestRef | str
    source_sql_bytes: int
    table_count: int
    row_count_total: int
    repository_id: str
    before_repository_ref: str
    current_repository_ref: str
    comparison_mode: str = "DOLT_TO_DOLT"
    pair_count: int = 1
    stages: tuple[HistoryCompareBenchmarkStageResult, ...] = field(default_factory=tuple)
    comparison_status: str | None = None
    comparison_duration_ms: int | None = None
    risk_duration_ms: int | None = None
    surface_duration_ms: int | None = None
    bundle_duration_ms: int | None = None
    native_route_count: int | None = None
    cache_hit_count: int | None = None
    cache_miss_count: int | None = None
    comparison_core_cache_hit_count: int | None = None
    comparison_core_cache_miss_count: int | None = None
    comparison_core_cache_completion_ms: int | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "dataset_kind", "repository_id", "before_repository_ref", "current_repository_ref", "comparison_mode"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "profile", HistoryCompareBenchmarkProfile(self.profile))
        object.__setattr__(self, "provider", RepositoryImportProvider(self.provider))
        object.__setattr__(self, "status", HistoryCompareBenchmarkStatus(self.status))
        object.__setattr__(self, "source_sql_digest", DigestRef.parse(str(self.source_sql_digest)))
        for field_name in ("source_sql_bytes", "table_count", "row_count_total"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.pair_count, int) or isinstance(self.pair_count, bool) or self.pair_count <= 0:
            raise ValueError("pair_count must be a positive integer")
        if not isinstance(self.stages, tuple):
            object.__setattr__(self, "stages", tuple(self.stages))
        normalized_stages: list[HistoryCompareBenchmarkStageResult] = []
        for stage in self.stages:
            if not isinstance(stage, HistoryCompareBenchmarkStageResult):
                raise TypeError("stages must contain HistoryCompareBenchmarkStageResult values")
            normalized_stages.append(stage)
        object.__setattr__(self, "stages", tuple(normalized_stages))
        if self.comparison_status is not None and (
            not isinstance(self.comparison_status, str) or not self.comparison_status
        ):
            raise ValueError("comparison_status must be a non-empty string or None")
        for field_name in (
            "comparison_duration_ms",
            "risk_duration_ms",
            "surface_duration_ms",
            "bundle_duration_ms",
            "native_route_count",
            "cache_hit_count",
            "cache_miss_count",
            "comparison_core_cache_hit_count",
            "comparison_core_cache_miss_count",
            "comparison_core_cache_completion_ms",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.failure_stage is not None and (
            not isinstance(self.failure_stage, str) or not self.failure_stage
        ):
            raise ValueError("failure_stage must be a non-empty string or None")
        if self.failure_reason is not None and (
            not isinstance(self.failure_reason, str) or not self.failure_reason
        ):
            raise ValueError("failure_reason must be a non-empty string or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    @property
    def total_duration_ms(self) -> int:
        return sum(stage.duration_ms for stage in self.stages)

    def stage(self, stage_name: str) -> HistoryCompareBenchmarkStageResult | None:
        normalized = stage_name.strip()
        for stage in self.stages:
            if stage.stage_name == normalized:
                return stage
        return None

    def stage_duration(self, stage_name: str) -> int | None:
        stage = self.stage(stage_name)
        if stage is None:
            return None
        return stage.duration_ms

    def stage_details(self, stage_name: str) -> Mapping[str, object] | None:
        stage = self.stage(stage_name)
        if stage is None:
            return None
        return stage.details

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "profile": self.profile.value,
            "provider": self.provider.value,
            "status": self.status.value,
            "source_sql_digest": self.source_sql_digest.to_payload(),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "repository_id": self.repository_id,
            "before_repository_ref": self.before_repository_ref,
            "current_repository_ref": self.current_repository_ref,
            "comparison_mode": self.comparison_mode,
            "pair_count": self.pair_count,
            "stages": [stage.to_payload() for stage in self.stages],
            "comparison_status": self.comparison_status,
            "comparison_duration_ms": self.comparison_duration_ms,
            "risk_duration_ms": self.risk_duration_ms,
            "surface_duration_ms": self.surface_duration_ms,
            "bundle_duration_ms": self.bundle_duration_ms,
            "native_route_count": self.native_route_count,
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "comparison_core_cache_hit_count": self.comparison_core_cache_hit_count,
            "comparison_core_cache_miss_count": self.comparison_core_cache_miss_count,
            "comparison_core_cache_completion_ms": self.comparison_core_cache_completion_ms,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "total_duration_ms": self.total_duration_ms,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "HistoryCompareBenchmarkResult":
        stages_payload = payload.get("stages", [])
        if stages_payload is None:
            stages_payload = []
        if not isinstance(stages_payload, Sequence):
            raise TypeError("stages payload must be a sequence")
        stages = tuple(
            HistoryCompareBenchmarkStageResult.from_payload(stage)
            for stage in stages_payload
        )
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, Sequence):
            raise TypeError("diagnostics payload must be a sequence")
        diagnostics = tuple(
            DiagnosticRecord.from_payload(diagnostic)
            for diagnostic in diagnostics_payload
        )
        return cls(
            dataset_id=_required_str(payload, "dataset_id"),
            dataset_kind=_required_str(payload, "dataset_kind"),
            profile=_required_str(payload, "profile"),
            provider=_required_str(payload, "provider"),
            status=_required_str(payload, "status"),
            source_sql_digest=DigestRef.parse(_required_str(payload, "source_sql_digest")),
            source_sql_bytes=_optional_int(payload.get("source_sql_bytes"), field_name="source_sql_bytes") or 0,
            table_count=_optional_int(payload.get("table_count"), field_name="table_count") or 0,
            row_count_total=_optional_int(payload.get("row_count_total"), field_name="row_count_total") or 0,
            repository_id=_required_str(payload, "repository_id"),
            before_repository_ref=_required_str(payload, "before_repository_ref"),
            current_repository_ref=_required_str(payload, "current_repository_ref"),
            comparison_mode=_optional_str(payload.get("comparison_mode"), field_name="comparison_mode") or "DOLT_TO_DOLT",
            pair_count=_optional_int(payload.get("pair_count"), field_name="pair_count") or 1,
            stages=stages,
            comparison_status=_optional_str(payload.get("comparison_status"), field_name="comparison_status"),
            comparison_duration_ms=_optional_int(payload.get("comparison_duration_ms"), field_name="comparison_duration_ms"),
            risk_duration_ms=_optional_int(payload.get("risk_duration_ms"), field_name="risk_duration_ms"),
            surface_duration_ms=_optional_int(payload.get("surface_duration_ms"), field_name="surface_duration_ms"),
            bundle_duration_ms=_optional_int(payload.get("bundle_duration_ms"), field_name="bundle_duration_ms"),
            native_route_count=_optional_int(payload.get("native_route_count"), field_name="native_route_count"),
            cache_hit_count=_optional_int(payload.get("cache_hit_count"), field_name="cache_hit_count"),
            cache_miss_count=_optional_int(payload.get("cache_miss_count"), field_name="cache_miss_count"),
            comparison_core_cache_hit_count=_optional_int(
                payload.get("comparison_core_cache_hit_count"),
                field_name="comparison_core_cache_hit_count",
            ),
            comparison_core_cache_miss_count=_optional_int(
                payload.get("comparison_core_cache_miss_count"),
                field_name="comparison_core_cache_miss_count",
            ),
            comparison_core_cache_completion_ms=_optional_int(
                payload.get("comparison_core_cache_completion_ms"),
                field_name="comparison_core_cache_completion_ms",
            ),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class HistoryCompareBenchmarkSummary:
    run_id: str
    created_at: datetime
    machine_profile: RepositoryImportBenchmarkMachineProfile
    datasets: tuple[RepositoryImportBenchmarkDatasetManifest, ...]
    profiles: tuple[HistoryCompareBenchmarkProfile | str, ...]
    providers: tuple[str, ...]
    results: tuple[HistoryCompareBenchmarkResult, ...]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(self.machine_profile, RepositoryImportBenchmarkMachineProfile):
            raise TypeError(
                "machine_profile must be a RepositoryImportBenchmarkMachineProfile"
            )
        if not isinstance(self.datasets, tuple):
            object.__setattr__(self, "datasets", tuple(self.datasets))
        for dataset in self.datasets:
            if not isinstance(dataset, RepositoryImportBenchmarkDatasetManifest):
                raise TypeError("datasets must contain RepositoryImportBenchmarkDatasetManifest values")
        normalized_profiles: list[HistoryCompareBenchmarkProfile] = []
        for profile in self.profiles:
            normalized_profiles.append(HistoryCompareBenchmarkProfile(profile))
        object.__setattr__(self, "profiles", tuple(normalized_profiles))
        if not isinstance(self.providers, tuple):
            object.__setattr__(self, "providers", tuple(self.providers))
        normalized_providers: list[str] = []
        seen_providers: set[str] = set()
        for provider in self.providers:
            if not isinstance(provider, str) or not provider:
                raise ValueError("providers must contain non-empty strings")
            if provider in seen_providers:
                continue
            seen_providers.add(provider)
            normalized_providers.append(provider)
        object.__setattr__(self, "providers", tuple(normalized_providers))
        if not isinstance(self.results, tuple):
            object.__setattr__(self, "results", tuple(self.results))
        normalized_results: list[HistoryCompareBenchmarkResult] = []
        for result in self.results:
            if not isinstance(result, HistoryCompareBenchmarkResult):
                raise TypeError("results must contain HistoryCompareBenchmarkResult values")
            normalized_results.append(result)
        object.__setattr__(self, "results", tuple(normalized_results))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "machine_profile": self.machine_profile.to_payload(),
            "datasets": [_payload_value(dataset) for dataset in self.datasets],
            "profiles": [profile.value for profile in self.profiles],
            "providers": list(self.providers),
            "results": [result.to_payload() for result in self.results],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "HistoryCompareBenchmarkSummary":
        datasets_payload = payload.get("datasets", [])
        if datasets_payload is None:
            datasets_payload = []
        if not isinstance(datasets_payload, Sequence):
            raise TypeError("datasets payload must be a sequence")
        results_payload = payload.get("results", [])
        if results_payload is None:
            results_payload = []
        if not isinstance(results_payload, Sequence):
            raise TypeError("results payload must be a sequence")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, Sequence):
            raise TypeError("diagnostics payload must be a sequence")
        return cls(
            run_id=_required_str(payload, "run_id"),
            created_at=datetime.fromisoformat(_required_str(payload, "created_at")),
            machine_profile=RepositoryImportBenchmarkMachineProfile.from_payload(
                payload.get("machine_profile", {})
            ),
            datasets=tuple(
                RepositoryImportBenchmarkDatasetManifest.from_payload(dataset)
                for dataset in datasets_payload
            ),
            profiles=tuple(payload.get("profiles", ())),
            providers=tuple(str(provider) for provider in payload.get("providers", ())),
            results=tuple(
                HistoryCompareBenchmarkResult.from_payload(result)
                for result in results_payload
            ),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                for diagnostic in diagnostics_payload
            ),
        )
