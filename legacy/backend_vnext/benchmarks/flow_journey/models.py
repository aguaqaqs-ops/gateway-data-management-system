from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from datetime import datetime

from ...core import DigestRef, DiagnosticRecord
from ..repository_import import (
    RepositoryImportBenchmarkDatasetManifest,
    RepositoryImportBenchmarkMachineProfile,
)
from ...capabilities.repository_import import RepositoryImportProvider


class FlowJourneyBenchmarkProfile(StrEnum):
    FULL_JOURNEY_COLD = "FULL_JOURNEY_COLD"
    FULL_JOURNEY_WARM = "FULL_JOURNEY_WARM"


class FlowJourneyBenchmarkStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class FlowJourneyBenchmarkSubmissionKind(StrEnum):
    BASELINE_INIT_SUBMISSION = "BASELINE_INIT_SUBMISSION"
    INITIAL_MODIFIED_SUBMISSION = "INITIAL_MODIFIED_SUBMISSION"


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
    if isinstance(value, Enum):
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
class FlowJourneyBenchmarkStageResult:
    stage_name: str
    status: str
    duration_ms: int
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.stage_name, str) or not self.stage_name:
            raise ValueError("stage_name must be a non-empty string")
        if not isinstance(self.status, str) or not self.status:
            raise ValueError("status must be a non-empty string")
        if not isinstance(self.duration_ms, int) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative integer")
        if not isinstance(self.details, Mapping):
            raise TypeError("details must be a mapping")
        normalized_details: dict[str, object] = {}
        for key, value in self.details.items():
            if not isinstance(key, str) or not key:
                raise TypeError("details keys must be non-empty strings")
            normalized_details[key] = value
        object.__setattr__(self, "details", normalized_details)

    def to_payload(self) -> dict[str, object]:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "details": _payload_value(self.details),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "FlowJourneyBenchmarkStageResult":
        details = payload.get("details", {})
        if details is None:
            details = {}
        if not isinstance(details, Mapping):
            raise TypeError("stage details payload must be a mapping")
        return cls(
            stage_name=_required_str(payload, "stage_name"),
            status=_required_str(payload, "status"),
            duration_ms=_required_int(payload, "duration_ms"),
            details=details,
        )


@dataclass(frozen=True, slots=True)
class FlowJourneyBenchmarkResult:
    dataset_id: str
    dataset_kind: str
    profile: FlowJourneyBenchmarkProfile | str
    provider: RepositoryImportProvider | str
    status: FlowJourneyBenchmarkStatus | str
    source_sql_digest: DigestRef | str
    source_sql_bytes: int
    table_count: int
    row_count_total: int
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    workspace_id: str | None = None
    submission_id: str | None = None
    repository_id: str | None = None
    repository_path: Path | None = None
    repository_commit_hash: str | None = None
    stages: tuple[FlowJourneyBenchmarkStageResult, ...] = field(default_factory=tuple)
    failure_stage: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    submission_kind: FlowJourneyBenchmarkSubmissionKind | str = FlowJourneyBenchmarkSubmissionKind.INITIAL_MODIFIED_SUBMISSION

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "dataset_kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "profile", FlowJourneyBenchmarkProfile(self.profile))
        object.__setattr__(self, "provider", RepositoryImportProvider(self.provider))
        object.__setattr__(self, "submission_kind", FlowJourneyBenchmarkSubmissionKind(self.submission_kind))
        object.__setattr__(self, "status", FlowJourneyBenchmarkStatus(self.status))
        object.__setattr__(self, "source_sql_digest", DigestRef.parse(str(self.source_sql_digest)))
        for field_name in ("source_sql_bytes", "table_count", "row_count_total"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        normalized_requested_tables: list[str] = []
        seen_requested_tables: set[str] = set()
        for table_name in self.requested_tables:
            if not isinstance(table_name, str) or not table_name:
                raise ValueError("requested_tables must contain non-empty strings")
            if table_name in seen_requested_tables:
                continue
            seen_requested_tables.add(table_name)
            normalized_requested_tables.append(table_name)
        object.__setattr__(self, "requested_tables", tuple(normalized_requested_tables))
        if self.workspace_id is not None and (not isinstance(self.workspace_id, str) or not self.workspace_id):
            raise ValueError("workspace_id must be a non-empty string or None")
        if self.submission_id is not None and (not isinstance(self.submission_id, str) or not self.submission_id):
            raise ValueError("submission_id must be a non-empty string or None")
        if self.repository_id is not None and (not isinstance(self.repository_id, str) or not self.repository_id):
            raise ValueError("repository_id must be a non-empty string or None")
        if self.repository_path is not None and not isinstance(self.repository_path, Path):
            raise TypeError("repository_path must be a Path or None")
        if self.repository_commit_hash is not None and (
            not isinstance(self.repository_commit_hash, str) or not self.repository_commit_hash
        ):
            raise ValueError("repository_commit_hash must be a non-empty string or None")
        if self.failure_stage is not None and (not isinstance(self.failure_stage, str) or not self.failure_stage):
            raise ValueError("failure_stage must be a non-empty string or None")
        if self.failure_reason is not None and (not isinstance(self.failure_reason, str) or not self.failure_reason):
            raise ValueError("failure_reason must be a non-empty string or None")
        if not isinstance(self.stages, tuple):
            object.__setattr__(self, "stages", tuple(self.stages))
        normalized_stages: list[FlowJourneyBenchmarkStageResult] = []
        for stage in self.stages:
            if not isinstance(stage, FlowJourneyBenchmarkStageResult):
                raise TypeError("stages must contain FlowJourneyBenchmarkStageResult values")
            normalized_stages.append(stage)
        object.__setattr__(self, "stages", tuple(normalized_stages))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    @property
    def total_duration_ms(self) -> int:
        return sum(stage.duration_ms for stage in self.stages)

    def stage(self, stage_name: str) -> FlowJourneyBenchmarkStageResult | None:
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
            "submission_kind": self.submission_kind.value,
            "status": self.status.value,
            "source_sql_digest": self.source_sql_digest.to_payload(),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "requested_tables": list(self.requested_tables),
            "workspace_id": self.workspace_id,
            "submission_id": self.submission_id,
            "repository_id": self.repository_id,
            "repository_path": None if self.repository_path is None else str(self.repository_path),
            "repository_commit_hash": self.repository_commit_hash,
            "stages": [stage.to_payload() for stage in self.stages],
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "total_duration_ms": self.total_duration_ms,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "FlowJourneyBenchmarkResult":
        stages_payload = payload.get("stages", [])
        if stages_payload is None:
            stages_payload = []
        if not isinstance(stages_payload, list):
            raise TypeError("stages payload must be a list")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("diagnostics payload must be a list")
        requested_tables = payload.get("requested_tables", [])
        if requested_tables is None:
            requested_tables = []
        if not isinstance(requested_tables, list):
            raise TypeError("requested_tables payload must be a list")
        return cls(
            dataset_id=_required_str(payload, "dataset_id"),
            dataset_kind=_required_str(payload, "dataset_kind"),
            profile=_required_str(payload, "profile"),
            provider=_required_str(payload, "provider"),
            submission_kind=_optional_str(payload.get("submission_kind"), field_name="submission_kind")
            or FlowJourneyBenchmarkSubmissionKind.INITIAL_MODIFIED_SUBMISSION.value,
            status=_required_str(payload, "status"),
            source_sql_digest=_required_str(payload, "source_sql_digest"),
            source_sql_bytes=_required_int(payload, "source_sql_bytes"),
            table_count=_required_int(payload, "table_count"),
            row_count_total=_required_int(payload, "row_count_total"),
            requested_tables=tuple(str(item) for item in requested_tables),
            workspace_id=_optional_str(payload.get("workspace_id"), field_name="workspace_id"),
            submission_id=_optional_str(payload.get("submission_id"), field_name="submission_id"),
            repository_id=_optional_str(payload.get("repository_id"), field_name="repository_id"),
            repository_path=(
                None
                if payload.get("repository_path") is None
                else Path(str(payload["repository_path"]))
            ),
            repository_commit_hash=_optional_str(
                payload.get("repository_commit_hash"),
                field_name="repository_commit_hash",
            ),
            stages=tuple(FlowJourneyBenchmarkStageResult.from_payload(_require_mapping(item, "stages item")) for item in stages_payload),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            diagnostics=tuple(DiagnosticRecord.from_payload(item) for item in diagnostics_payload),
        )


@dataclass(frozen=True, slots=True)
class FlowJourneyBenchmarkSummary:
    run_id: str
    created_at: str
    machine_profile: RepositoryImportBenchmarkMachineProfile
    datasets: tuple[RepositoryImportBenchmarkDatasetManifest, ...]
    profiles: tuple[str, ...]
    providers: tuple[str, ...]
    results: tuple[FlowJourneyBenchmarkResult, ...]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("created_at must be a non-empty string")
        if not isinstance(self.machine_profile, RepositoryImportBenchmarkMachineProfile):
            raise TypeError("machine_profile must be a RepositoryImportBenchmarkMachineProfile")
        if not isinstance(self.datasets, tuple):
            object.__setattr__(self, "datasets", tuple(self.datasets))
        normalized_datasets: list[RepositoryImportBenchmarkDatasetManifest] = []
        for dataset in self.datasets:
            if not isinstance(dataset, RepositoryImportBenchmarkDatasetManifest):
                raise TypeError("datasets must contain RepositoryImportBenchmarkDatasetManifest values")
            normalized_datasets.append(dataset)
        object.__setattr__(self, "datasets", tuple(normalized_datasets))
        object.__setattr__(self, "profiles", tuple(str(profile) for profile in self.profiles))
        object.__setattr__(self, "providers", tuple(str(provider) for provider in self.providers))
        if not isinstance(self.results, tuple):
            object.__setattr__(self, "results", tuple(self.results))
        normalized_results: list[FlowJourneyBenchmarkResult] = []
        for result in self.results:
            if not isinstance(result, FlowJourneyBenchmarkResult):
                raise TypeError("results must contain FlowJourneyBenchmarkResult values")
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
            "created_at": self.created_at,
            "machine_profile": self.machine_profile.to_payload(),
            "datasets": [dataset.to_payload() for dataset in self.datasets],
            "profiles": list(self.profiles),
            "providers": list(self.providers),
            "results": [result.to_payload() for result in self.results],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "FlowJourneyBenchmarkSummary":
        datasets_payload = payload.get("datasets", [])
        if datasets_payload is None:
            datasets_payload = []
        if not isinstance(datasets_payload, list):
            raise TypeError("summary datasets payload must be a list")
        profiles_payload = payload.get("profiles", [])
        if profiles_payload is None:
            profiles_payload = []
        if not isinstance(profiles_payload, list):
            raise TypeError("summary profiles payload must be a list")
        providers_payload = payload.get("providers", [])
        if providers_payload is None:
            providers_payload = []
        if not isinstance(providers_payload, list):
            raise TypeError("summary providers payload must be a list")
        results_payload = payload.get("results", [])
        if results_payload is None:
            results_payload = []
        if not isinstance(results_payload, list):
            raise TypeError("summary results payload must be a list")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("summary diagnostics payload must be a list")
        return cls(
            run_id=_required_str(payload, "run_id"),
            created_at=_required_str(payload, "created_at"),
            machine_profile=RepositoryImportBenchmarkMachineProfile.from_payload(
                _require_mapping(payload["machine_profile"], "machine_profile")
            ),
            datasets=tuple(
                RepositoryImportBenchmarkDatasetManifest.from_payload(_require_mapping(item, "datasets item"))
                for item in datasets_payload
            ),
            profiles=tuple(str(item) for item in profiles_payload),
            providers=tuple(str(item) for item in providers_payload),
            results=tuple(
                FlowJourneyBenchmarkResult.from_payload(_require_mapping(item, "results item"))
                for item in results_payload
            ),
            diagnostics=tuple(DiagnosticRecord.from_payload(item) for item in diagnostics_payload),
        )


def _require_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload[field_name]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _required_int(payload: Mapping[str, object], field_name: str) -> int:
    return _require_int(payload, field_name)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value
