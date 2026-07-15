from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ...core import DigestRef, DiagnosticRecord
from ..flow_journey.models import FlowJourneyBenchmarkStageResult
from ..repository_import import RepositoryImportBenchmarkMachineProfile
from ..history_compare.models import HistoryCompareBenchmarkStageResult


WorkflowLadderBenchmarkStageResult = FlowJourneyBenchmarkStageResult


class WorkflowLadderBenchmarkStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


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


def _optional_path(value: object, *, field_name: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return Path(value)


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _optional_stage_list(
    value: object,
    *,
    field_name: str,
) -> tuple[FlowJourneyBenchmarkStageResult | HistoryCompareBenchmarkStageResult, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence):
        raise TypeError(f"{field_name} payload must be a sequence")
    stages: list[FlowJourneyBenchmarkStageResult | HistoryCompareBenchmarkStageResult] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(f"{field_name} payload must contain mappings")
        if field_name.endswith("compare_stages"):
            stages.append(HistoryCompareBenchmarkStageResult.from_payload(item))
        else:
            stages.append(FlowJourneyBenchmarkStageResult.from_payload(item))
    return tuple(stages)


@dataclass(frozen=True, slots=True)
class WorkflowLadderNodeResult:
    node_id: str
    dataset_id: str
    dataset_kind: str
    status: WorkflowLadderBenchmarkStatus | str
    source_sql_digest: DigestRef | str
    source_sql_bytes: int
    table_count: int
    row_count_total: int
    stages: tuple[FlowJourneyBenchmarkStageResult, ...] = field(default_factory=tuple)
    submission_kind: str = "INITIAL_MODIFIED_SUBMISSION"
    workspace_id: str | None = None
    submission_id: str | None = None
    repository_id: str | None = None
    repository_path: Path | None = None
    repository_commit_hash: str | None = None
    baseline_repository_ref: str | None = None
    current_repository_ref: str | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("node_id", "dataset_id", "dataset_kind", "submission_kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "status", WorkflowLadderBenchmarkStatus(self.status))
        object.__setattr__(self, "source_sql_digest", DigestRef.parse(str(self.source_sql_digest)))
        for field_name in ("source_sql_bytes", "table_count", "row_count_total"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.stages, tuple):
            object.__setattr__(self, "stages", tuple(self.stages))
        normalized_stages: list[FlowJourneyBenchmarkStageResult] = []
        for stage in self.stages:
            if not isinstance(stage, FlowJourneyBenchmarkStageResult):
                raise TypeError("stages must contain FlowJourneyBenchmarkStageResult values")
            normalized_stages.append(stage)
        object.__setattr__(self, "stages", tuple(normalized_stages))
        for field_name in ("workspace_id", "submission_id", "repository_id", "failure_stage", "failure_reason", "baseline_repository_ref", "current_repository_ref"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if self.repository_path is not None and not isinstance(self.repository_path, Path):
            raise TypeError("repository_path must be a Path or None")
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
            "node_id": self.node_id,
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "status": self.status.value,
            "source_sql_digest": self.source_sql_digest.to_payload(),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "stages": [stage.to_payload() for stage in self.stages],
            "submission_kind": self.submission_kind,
            "workspace_id": self.workspace_id,
            "submission_id": self.submission_id,
            "repository_id": self.repository_id,
            "repository_path": None if self.repository_path is None else str(self.repository_path),
            "repository_commit_hash": self.repository_commit_hash,
            "baseline_repository_ref": self.baseline_repository_ref,
            "current_repository_ref": self.current_repository_ref,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "WorkflowLadderNodeResult":
        stages_payload = payload.get("stages", [])
        if stages_payload is None:
            stages_payload = []
        if not isinstance(stages_payload, Sequence):
            raise TypeError("stages payload must be a sequence")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, Sequence):
            raise TypeError("diagnostics payload must be a sequence")
        return cls(
            node_id=_required_str(payload, "node_id"),
            dataset_id=_required_str(payload, "dataset_id"),
            dataset_kind=_required_str(payload, "dataset_kind"),
            status=_required_str(payload, "status"),
            source_sql_digest=_required_str(payload, "source_sql_digest"),
            source_sql_bytes=_optional_int(payload.get("source_sql_bytes"), field_name="source_sql_bytes") or 0,
            table_count=_optional_int(payload.get("table_count"), field_name="table_count") or 0,
            row_count_total=_optional_int(payload.get("row_count_total"), field_name="row_count_total") or 0,
            stages=tuple(
                FlowJourneyBenchmarkStageResult.from_payload(stage)
                for stage in stages_payload
            ),
            submission_kind=_required_str(payload, "submission_kind"),
            workspace_id=_optional_str(payload.get("workspace_id"), field_name="workspace_id"),
            submission_id=_optional_str(payload.get("submission_id"), field_name="submission_id"),
            repository_id=_optional_str(payload.get("repository_id"), field_name="repository_id"),
            repository_path=_optional_path(payload.get("repository_path"), field_name="repository_path"),
            repository_commit_hash=_optional_str(
                payload.get("repository_commit_hash"),
                field_name="repository_commit_hash",
            ),
            baseline_repository_ref=_optional_str(
                payload.get("baseline_repository_ref"),
                field_name="baseline_repository_ref",
            ),
            current_repository_ref=_optional_str(
                payload.get("current_repository_ref"),
                field_name="current_repository_ref",
            ),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                for diagnostic in diagnostics_payload
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowLadderCompareResult:
    scenario_name: str
    pair_ids: tuple[str, ...]
    pair_refs: tuple[tuple[str, str], ...]
    status: WorkflowLadderBenchmarkStatus | str
    source_sql_digest: DigestRef | str
    source_sql_bytes: int
    table_count: int
    row_count_total: int
    comparison_mode: str = "DOLT_TO_DOLT"
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
    comparison_core_cache_completion_pair_count: int | None = None
    comparison_core_cache_completion_write_count: int | None = None
    comparison_core_cache_completion_hit_count: int | None = None
    comparison_core_cache_completion_skip_count: int | None = None
    comparison_core_cache_completion_statuses: tuple[str, ...] = field(default_factory=tuple)
    failure_stage: str | None = None
    failure_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_name, str) or not self.scenario_name:
            raise ValueError("scenario_name must be a non-empty string")
        if not isinstance(self.pair_ids, tuple):
            object.__setattr__(self, "pair_ids", tuple(self.pair_ids))
        normalized_pair_ids: list[str] = []
        for pair_id in self.pair_ids:
            if not isinstance(pair_id, str) or not pair_id:
                raise ValueError("pair_ids must contain non-empty strings")
            normalized_pair_ids.append(pair_id)
        object.__setattr__(self, "pair_ids", tuple(normalized_pair_ids))
        if not isinstance(self.pair_refs, tuple):
            object.__setattr__(self, "pair_refs", tuple(tuple(item) for item in self.pair_refs))
        normalized_pair_refs: list[tuple[str, str]] = []
        for pair_ref in self.pair_refs:
            if not isinstance(pair_ref, tuple) or len(pair_ref) != 2:
                raise TypeError("pair_refs must contain 2-tuples")
            before_ref, current_ref = pair_ref
            if not isinstance(before_ref, str) or not before_ref:
                raise ValueError("pair_refs must contain non-empty strings")
            if not isinstance(current_ref, str) or not current_ref:
                raise ValueError("pair_refs must contain non-empty strings")
            normalized_pair_refs.append((before_ref, current_ref))
        object.__setattr__(self, "pair_refs", tuple(normalized_pair_refs))
        object.__setattr__(self, "status", WorkflowLadderBenchmarkStatus(self.status))
        object.__setattr__(self, "source_sql_digest", DigestRef.parse(str(self.source_sql_digest)))
        for field_name in ("source_sql_bytes", "table_count", "row_count_total"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("comparison_mode", "comparison_status", "failure_stage", "failure_reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if not isinstance(self.stages, tuple):
            object.__setattr__(self, "stages", tuple(self.stages))
        normalized_stages: list[HistoryCompareBenchmarkStageResult] = []
        for stage in self.stages:
            if not isinstance(stage, HistoryCompareBenchmarkStageResult):
                raise TypeError("stages must contain HistoryCompareBenchmarkStageResult values")
            normalized_stages.append(stage)
        object.__setattr__(self, "stages", tuple(normalized_stages))
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
            "comparison_core_cache_completion_pair_count",
            "comparison_core_cache_completion_write_count",
            "comparison_core_cache_completion_hit_count",
            "comparison_core_cache_completion_skip_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if not isinstance(self.comparison_core_cache_completion_statuses, tuple):
            object.__setattr__(
                self,
                "comparison_core_cache_completion_statuses",
                tuple(self.comparison_core_cache_completion_statuses),
            )
        normalized_statuses: list[str] = []
        for status in self.comparison_core_cache_completion_statuses:
            if not isinstance(status, str) or not status:
                raise ValueError("comparison_core_cache_completion_statuses must contain non-empty strings")
            normalized_statuses.append(status)
        object.__setattr__(self, "comparison_core_cache_completion_statuses", tuple(normalized_statuses))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    @property
    def pair_count(self) -> int:
        return len(self.pair_ids)

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

    @property
    def total_duration_ms(self) -> int:
        return sum(stage.duration_ms for stage in self.stages)

    def to_payload(self) -> dict[str, object]:
        return {
            "scenario_name": self.scenario_name,
            "pair_ids": list(self.pair_ids),
            "pair_refs": [list(pair_ref) for pair_ref in self.pair_refs],
            "status": self.status.value,
            "source_sql_digest": self.source_sql_digest.to_payload(),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "comparison_mode": self.comparison_mode,
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
            "comparison_core_cache_completion_pair_count": self.comparison_core_cache_completion_pair_count,
            "comparison_core_cache_completion_write_count": self.comparison_core_cache_completion_write_count,
            "comparison_core_cache_completion_hit_count": self.comparison_core_cache_completion_hit_count,
            "comparison_core_cache_completion_skip_count": self.comparison_core_cache_completion_skip_count,
            "comparison_core_cache_completion_statuses": list(self.comparison_core_cache_completion_statuses),
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "WorkflowLadderCompareResult":
        stages_payload = payload.get("stages", [])
        if stages_payload is None:
            stages_payload = []
        if not isinstance(stages_payload, Sequence):
            raise TypeError("stages payload must be a sequence")
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, Sequence):
            raise TypeError("diagnostics payload must be a sequence")
        pair_ids_payload = payload.get("pair_ids", [])
        if pair_ids_payload is None:
            pair_ids_payload = []
        if not isinstance(pair_ids_payload, Sequence):
            raise TypeError("pair_ids payload must be a sequence")
        pair_refs_payload = payload.get("pair_refs", [])
        if pair_refs_payload is None:
            pair_refs_payload = []
        if not isinstance(pair_refs_payload, Sequence):
            raise TypeError("pair_refs payload must be a sequence")
        completion_statuses_payload = payload.get("comparison_core_cache_completion_statuses", [])
        if completion_statuses_payload is None:
            completion_statuses_payload = []
        if not isinstance(completion_statuses_payload, Sequence):
            raise TypeError("comparison_core_cache_completion_statuses payload must be a sequence")
        return cls(
            scenario_name=_required_str(payload, "scenario_name"),
            pair_ids=tuple(str(item) for item in pair_ids_payload),
            pair_refs=tuple(
                (str(pair_ref[0]), str(pair_ref[1]))
                for pair_ref in pair_refs_payload
            ),
            status=_required_str(payload, "status"),
            source_sql_digest=_required_str(payload, "source_sql_digest"),
            source_sql_bytes=_optional_int(payload.get("source_sql_bytes"), field_name="source_sql_bytes") or 0,
            table_count=_optional_int(payload.get("table_count"), field_name="table_count") or 0,
            row_count_total=_optional_int(payload.get("row_count_total"), field_name="row_count_total") or 0,
            comparison_mode=_optional_str(payload.get("comparison_mode"), field_name="comparison_mode") or "DOLT_TO_DOLT",
            stages=tuple(
                HistoryCompareBenchmarkStageResult.from_payload(stage)
                for stage in stages_payload
            ),
            comparison_status=_optional_str(
                payload.get("comparison_status"),
                field_name="comparison_status",
            ),
            comparison_duration_ms=_optional_int(
                payload.get("comparison_duration_ms"),
                field_name="comparison_duration_ms",
            ),
            risk_duration_ms=_optional_int(payload.get("risk_duration_ms"), field_name="risk_duration_ms"),
            surface_duration_ms=_optional_int(
                payload.get("surface_duration_ms"),
                field_name="surface_duration_ms",
            ),
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
            comparison_core_cache_completion_pair_count=_optional_int(
                payload.get("comparison_core_cache_completion_pair_count"),
                field_name="comparison_core_cache_completion_pair_count",
            ),
            comparison_core_cache_completion_write_count=_optional_int(
                payload.get("comparison_core_cache_completion_write_count"),
                field_name="comparison_core_cache_completion_write_count",
            ),
            comparison_core_cache_completion_hit_count=_optional_int(
                payload.get("comparison_core_cache_completion_hit_count"),
                field_name="comparison_core_cache_completion_hit_count",
            ),
            comparison_core_cache_completion_skip_count=_optional_int(
                payload.get("comparison_core_cache_completion_skip_count"),
                field_name="comparison_core_cache_completion_skip_count",
            ),
            comparison_core_cache_completion_statuses=tuple(str(item) for item in completion_statuses_payload),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                for diagnostic in diagnostics_payload
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkflowLadderBenchmarkSummary:
    run_id: str
    created_at: datetime
    machine_profile: RepositoryImportBenchmarkMachineProfile
    dataset_ids: tuple[str, ...]
    execution_order: tuple[str, ...]
    status: WorkflowLadderBenchmarkStatus | str
    node_results: tuple[WorkflowLadderNodeResult, ...] = field(default_factory=tuple)
    compare_results: tuple[WorkflowLadderCompareResult, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    failure_stage: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if not isinstance(self.machine_profile, RepositoryImportBenchmarkMachineProfile):
            raise TypeError("machine_profile must be a RepositoryImportBenchmarkMachineProfile")
        if not isinstance(self.dataset_ids, tuple):
            object.__setattr__(self, "dataset_ids", tuple(self.dataset_ids))
        normalized_dataset_ids: list[str] = []
        seen_dataset_ids: set[str] = set()
        for dataset_id in self.dataset_ids:
            if not isinstance(dataset_id, str) or not dataset_id:
                raise ValueError("dataset_ids must contain non-empty strings")
            if dataset_id in seen_dataset_ids:
                continue
            seen_dataset_ids.add(dataset_id)
            normalized_dataset_ids.append(dataset_id)
        object.__setattr__(self, "dataset_ids", tuple(normalized_dataset_ids))
        if not isinstance(self.execution_order, tuple):
            object.__setattr__(self, "execution_order", tuple(self.execution_order))
        normalized_execution_order: list[str] = []
        for step in self.execution_order:
            if not isinstance(step, str) or not step:
                raise ValueError("execution_order must contain non-empty strings")
            normalized_execution_order.append(step)
        object.__setattr__(self, "execution_order", tuple(normalized_execution_order))
        object.__setattr__(self, "status", WorkflowLadderBenchmarkStatus(self.status))
        if not isinstance(self.node_results, tuple):
            object.__setattr__(self, "node_results", tuple(self.node_results))
        normalized_node_results: list[WorkflowLadderNodeResult] = []
        for node_result in self.node_results:
            if not isinstance(node_result, WorkflowLadderNodeResult):
                raise TypeError("node_results must contain WorkflowLadderNodeResult values")
            normalized_node_results.append(node_result)
        object.__setattr__(self, "node_results", tuple(normalized_node_results))
        if not isinstance(self.compare_results, tuple):
            object.__setattr__(self, "compare_results", tuple(self.compare_results))
        normalized_compare_results: list[WorkflowLadderCompareResult] = []
        for compare_result in self.compare_results:
            if not isinstance(compare_result, WorkflowLadderCompareResult):
                raise TypeError("compare_results must contain WorkflowLadderCompareResult values")
            normalized_compare_results.append(compare_result)
        object.__setattr__(self, "compare_results", tuple(normalized_compare_results))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if self.failure_stage is not None and (not isinstance(self.failure_stage, str) or not self.failure_stage):
            raise ValueError("failure_stage must be a non-empty string or None")
        if self.failure_reason is not None and (not isinstance(self.failure_reason, str) or not self.failure_reason):
            raise ValueError("failure_reason must be a non-empty string or None")

    @property
    def total_duration_ms(self) -> int:
        return sum(node.total_duration_ms for node in self.node_results) + sum(
            compare.total_duration_ms for compare in self.compare_results
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "machine_profile": self.machine_profile.to_payload(),
            "dataset_ids": list(self.dataset_ids),
            "execution_order": list(self.execution_order),
            "status": self.status.value,
            "node_results": [node_result.to_payload() for node_result in self.node_results],
            "compare_results": [compare_result.to_payload() for compare_result in self.compare_results],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "total_duration_ms": self.total_duration_ms,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "WorkflowLadderBenchmarkSummary":
        node_results_payload = payload.get("node_results", [])
        if node_results_payload is None:
            node_results_payload = []
        if not isinstance(node_results_payload, Sequence):
            raise TypeError("node_results payload must be a sequence")
        compare_results_payload = payload.get("compare_results", [])
        if compare_results_payload is None:
            compare_results_payload = []
        if not isinstance(compare_results_payload, Sequence):
            raise TypeError("compare_results payload must be a sequence")
        dataset_ids_payload = payload.get("dataset_ids", [])
        if dataset_ids_payload is None:
            dataset_ids_payload = []
        if not isinstance(dataset_ids_payload, Sequence):
            raise TypeError("dataset_ids payload must be a sequence")
        execution_order_payload = payload.get("execution_order", [])
        if execution_order_payload is None:
            execution_order_payload = []
        if not isinstance(execution_order_payload, Sequence):
            raise TypeError("execution_order payload must be a sequence")
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
            dataset_ids=tuple(str(item) for item in dataset_ids_payload),
            execution_order=tuple(str(item) for item in execution_order_payload),
            status=_required_str(payload, "status"),
            node_results=tuple(
                WorkflowLadderNodeResult.from_payload(item)
                for item in node_results_payload
            ),
            compare_results=tuple(
                WorkflowLadderCompareResult.from_payload(item)
                for item in compare_results_payload
            ),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(diagnostic)
                for diagnostic in diagnostics_payload
            ),
            failure_stage=_optional_str(payload.get("failure_stage"), field_name="failure_stage"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
        )


WorkflowLadderBenchmarkNodeResult = WorkflowLadderNodeResult
WorkflowLadderBenchmarkCompareResult = WorkflowLadderCompareResult
